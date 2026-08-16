import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.identity.authorization import Actor, Role
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, Integration
from traderx.integrations.registry import approved_provider, validate_provider_configuration
from traderx.integrations.service import (
    ManagedIntegration,
    configure,
    create_non_broker_integration,
    integration_management_payload,
    rotate_integration_credentials,
    set_state,
    transition_persisted_integration,
)
from traderx.shared.db import Base, load_model_metadata
from traderx.shared.events import OutboxEvent


def test_only_allowlisted_read_capabilities_can_be_enabled() -> None:
    actor = Actor(Role.OWNER, "MFA")
    integration = configure(
        actor,
        ManagedIntegration("broker", "DISABLED", frozenset()),
        requested_capabilities={"ACCOUNT_READ"},
    )
    assert set_state(actor, integration, "ENABLED").state == "ENABLED"


def test_provider_registry_is_deny_by_default_and_mt5_is_read_only() -> None:
    mt5 = approved_provider("MT5_TERMINAL_BRIDGE")
    assert mt5.capabilities == {
        "ACCOUNT_READ",
        "INSTRUMENT_READ",
        "POSITION_READ",
        "DEAL_READ",
        "MARKET_DATA_READ",
    }
    with pytest.raises(ValueError, match="not approved"):
        approved_provider("UNREVIEWED_BROKER")


def test_official_source_and_provider_capability_policy_fail_closed() -> None:
    with pytest.raises(ValueError, match="official source"):
        validate_provider_configuration(
            "EMAIL",
            requested_capabilities={"NOTIFICATION_SEND"},
            configuration={"sender": "alerts@example.com", "recipient": "owner@example.com"},
            credentials={"api_token": "write-only"},
            official_source=False,
        )
    with pytest.raises(ValueError, match="outside"):
        validate_provider_configuration(
            "TELEGRAM",
            requested_capabilities={"ORDER_SEND"},
            configuration={"chat_id": "1"},
            credentials={"bot_token": "write-only"},
            official_source=True,
        )


def test_non_broker_lifecycle_rotation_and_reconnect_are_audited_and_write_only() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    box = SecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    actor = Actor(Role.OWNER, "MFA", uuid4())
    now = datetime(2026, 8, 14, tzinfo=UTC)
    try:
        with factory.begin() as database:
            integration = create_non_broker_integration(
                database,
                actor,
                provider="EMAIL",
                name="Owner email",
                configuration={
                    "sender": "alerts@example.com",
                    "recipient": "owner@example.com",
                },
                credentials={"api_token": "initial-private-token"},
                requested_capabilities={"NOTIFICATION_SEND"},
                official_source=True,
                secret_box=box,
                now=now,
                correlation_id="correlation-1",
                idempotency_key="integration-create-0001",
            )
            integration_id = integration.id

        with factory.begin() as database:
            integration = database.get(Integration, integration_id)
            assert integration is not None
            first = database.scalar(
                select(CredentialVersion).where(CredentialVersion.integration_id == integration_id)
            )
            assert first is not None
            assert "initial-private-token" not in first.encrypted_value
            rotated = rotate_integration_credentials(
                database,
                actor,
                integration,
                credentials={"api_token": "rotated-private-token"},
                secret_box=box,
                now=now,
                correlation_id="correlation-2",
                idempotency_key="integration-rotate-0001",
            )
            assert first.active is False
            assert box.decrypt(EncryptedSecret(**json.loads(rotated.encrypted_value))) == {
                "api_token": "rotated-private-token"
            }
            transition_persisted_integration(
                database,
                actor,
                integration,
                action="DISABLE",
                reason="Pause external email delivery",
                now=now,
                correlation_id="correlation-3",
                idempotency_key="integration-disable-0001",
            )
            assert integration.state == "DISABLED"
            transition_persisted_integration(
                database,
                actor,
                integration,
                action="RECONNECT",
                reason="Reconnect after credential rotation",
                now=now,
                correlation_id="correlation-4",
                idempotency_key="integration-reconnect-0001",
            )
            assert integration.state == "DEGRADED"
            public = integration_management_payload(database, integration)
            assert public["credential"] == "WRITE_ONLY"
            assert "rotated-private-token" not in json.dumps(public)
            outbox = list(database.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at)))
            assert len(outbox) == 4
            assert any(
                item.event_type == "com.traderx.integration.credential-rotated.v1"
                for item in outbox
            )
            assert "rotated-private-token" not in json.dumps(
                [item.envelope for item in outbox]
            )
    finally:
        engine.dispose()
