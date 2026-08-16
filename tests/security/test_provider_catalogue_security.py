from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.integrations.crypto import SecretBox
from traderx.integrations.model import CredentialVersion, Integration
from traderx.integrations.registry import approved_provider, validate_provider_configuration
from traderx.integrations.service import create_non_broker_integration
from traderx.shared.db import Base, load_model_metadata


def test_catalogue_rejects_arbitrary_endpoints_models_and_unreviewed_providers() -> None:
    with pytest.raises(ValueError, match="not approved"):
        approved_provider("USER_DEFINED_PROVIDER")
    with pytest.raises(ValueError, match="unapproved field"):
        validate_provider_configuration(
            "COINBASE_EXCHANGE",
            requested_capabilities={"MARKET_DATA_READ"},
            configuration={"base_url": "https://scraped.example"},
            credentials={},
            official_source=True,
        )
    definition = approved_provider("OPENAI_RESPONSES")
    assert "arbitrary-model" not in definition.permitted_models
    assert definition.fixed_base_url == "https://api.openai.com/v1"


def test_credentials_are_encrypted_and_never_projected_from_the_integration() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    actor = Actor(Role.OWNER, "MFA", uuid4())
    box = SecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    with Session(engine) as database, database.begin():
        integration = create_non_broker_integration(
            database,
            actor,
            provider="OPENAI_RESPONSES",
            name="Research OpenAI",
            configuration={},
            credentials={"api_key": "plaintext-must-not-persist"},
            requested_capabilities={"LLM_ANALYSIS"},
            official_source=True,
            secret_box=box,
            now=datetime(2026, 8, 14, tzinfo=UTC),
            correlation_id="catalogue-security",
            idempotency_key="catalogue-security-create-0001",
            licensing_accepted=True,
            retention_accepted=True,
        )
        credential = database.scalar(
            select(CredentialVersion).where(CredentialVersion.integration_id == integration.id)
        )
        assert credential is not None
        assert "plaintext-must-not-persist" not in credential.encrypted_value
        assert "plaintext-must-not-persist" not in str(integration.configuration)
        assert database.scalar(select(Integration)).provider == "OPENAI_RESPONSES"
