from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.accounts.model import PropProfileVersion, RiskPolicyVersion, TradingAccount
from traderx.identity.authorization import Actor, Role
from traderx.integrations.broker_model import BrokerIntegrationProfile, BrokerProvider
from traderx.integrations.broker_service import (
    BrokerIntegrationCommand,
    bind_selected_account,
    create_broker_integration,
    discovered_account_payload,
    record_discovered_accounts,
    rotate_broker_credential,
    sync_selected_broker_account,
)
from traderx.integrations.model import CredentialVersion
from traderx.risk.model import AccountSnapshot, RiskSnapshot
from traderx.shared.db import Base, load_model_metadata


def _session() -> tuple[Session, object]:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)(), engine


def test_oanda_credential_is_write_only_and_discovered_account_requires_explicit_binding() -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        integration = create_broker_integration(
            session,
            actor,
            BrokerIntegrationCommand(
                provider=BrokerProvider.OANDA_V20,
                configuration={"environment": "PRACTICE"},
                credentials={"personal_access_token": "not-returned-token"},
            ),
        )
        session.commit()

        profile = session.scalar(select(BrokerIntegrationProfile))
        stored = session.scalar(select(CredentialVersion))
        assert integration.provider == BrokerProvider.OANDA_V20
        assert profile.environment == "PRACTICE"
        assert profile.selected_provider_account_id is None
        assert "not-returned-token" not in stored.encrypted_value

        record_discovered_accounts(
            session,
            integration,
            [
                {
                    "provider_account_id": "001-001-123",
                    "display_name": "Practice",
                    "currency": "USD",
                    "account_mode": "PRACTICE",
                }
            ],
        )
        session.commit()
        candidate = discovered_account_payload(session, integration.id)[0]
        assert candidate == {
            "provider_account_id": "001-001-123",
            "provider": "OANDA_V20",
            "display_name": "Practice",
            "currency": "USD",
            "account_mode": "PRACTICE",
            "verification_status": "VERIFIED",
            "verified_at": candidate["verified_at"],
        }

        bind_selected_account(session, actor, integration, "001-001-123")
        session.commit()
        assert profile.selected_provider_account_id == "001-001-123"
    finally:
        session.close()
        engine.dispose()


def test_rotating_a_broker_credential_supersedes_previous_version() -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        integration = create_broker_integration(
            session,
            actor,
            BrokerIntegrationCommand(
                provider=BrokerProvider.MT5_TERMINAL_BRIDGE,
                configuration={
                    "bridge_url": "https://bridge.example.test",
                    "bridge_id": "bridge-1",
                    "account_login": "123456",
                    "server": "Demo-Server",
                },
                credentials={"bridge_client_secret": "initial-secret"},
            ),
        )
        rotate_broker_credential(
            session,
            actor,
            integration,
            {"bridge_client_secret": "rotated-secret"},
        )
        session.commit()

        credentials = session.scalars(
            select(CredentialVersion).where(CredentialVersion.integration_id == integration.id)
        ).all()
        assert len(credentials) == 2
        assert sum(credential.active for credential in credentials) == 1
        assert all("secret" not in credential.encrypted_value for credential in credentials)
    finally:
        session.close()
        engine.dispose()


def test_syncing_a_selected_oanda_account_commits_verified_account_and_risk_snapshot(monkeypatch) -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        integration = create_broker_integration(
            session,
            actor,
            BrokerIntegrationCommand(
                provider=BrokerProvider.OANDA_V20,
                configuration={"environment": "PRACTICE"},
                credentials={"personal_access_token": "practice-token"},
            ),
        )
        account = TradingAccount(
            name="Primary",
            mode="LIVE",
            currency="USD",
            starting_balance=Decimal("10000"),
            status="DRAFT",
        )
        session.add(account)
        session.flush()
        prop = PropProfileVersion(
            account_id=account.id,
            profile_version=1,
            daily_loss_limit=Decimal("500"),
            maximum_loss_limit=Decimal("1000"),
            trailing_drawdown=False,
            floating_loss_counts=True,
            reset_timezone="UTC",
            reset_time="00:00",
            restrictions={},
            effective_at=datetime(2026, 8, 13, tzinfo=UTC),
            reason="Initial external risk rules",
        )
        policy = RiskPolicyVersion(
            account_id=account.id,
            policy_version=1,
            maximum_risk_per_trade=Decimal("100"),
            maximum_portfolio_risk=Decimal("200"),
            internal_daily_loss_limit=Decimal("300"),
            internal_drawdown_limit=Decimal("600"),
            minimum_prop_buffer=Decimal("0"),
            maximum_positions=2,
            correlation_limit=Decimal("1"),
            state_thresholds={},
            effective_at=datetime(2026, 8, 13, tzinfo=UTC),
            reason="Initial internal risk rules",
        )
        session.add_all([prop, policy])
        session.flush()
        account.prop_profile_id = prop.id
        account.risk_policy_id = policy.id
        record_discovered_accounts(
            session,
            integration,
            [{"provider_account_id": "001-001-123", "currency": "USD", "account_mode": "PRACTICE"}],
        )
        bind_selected_account(session, actor, integration, "001-001-123")
        account.broker_integration_id = integration.id
        account.provider_account_id = "001-001-123"

        class FakeOanda:
            def __init__(self, **_: object) -> None:
                pass

            def close(self) -> None:
                pass

            def bootstrap_account(self, account_id: str):  # type: ignore[no-untyped-def]
                from traderx.integrations.oanda_v20 import OandaAccountSnapshot

                return OandaAccountSnapshot(
                    provider_account_id=account_id,
                    balance="10000.00",
                    equity="10020.00",
                    equity_source="NAV",
                    realized_pl="20.00",
                    floating_pl="0.00",
                    margin_available="9000.00",
                    open_position_count=0,
                    cursor="77",
                    observed_at=datetime(2026, 8, 13, tzinfo=UTC),
                    raw={},
                )

        monkeypatch.setattr("traderx.integrations.broker_service.OandaV20Adapter", FakeOanda)
        result = sync_selected_broker_account(session, integration, account)
        session.commit()

        assert result["quality"] == "VERIFIED"
        assert session.scalar(select(AccountSnapshot)).equity == Decimal("10020")
        risk = session.scalar(select(RiskSnapshot))
        assert risk is not None
        assert risk.state == "NORMAL"
        assert risk.capacity == 2
    finally:
        session.close()
        engine.dispose()
