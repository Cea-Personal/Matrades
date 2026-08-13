from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.accounts.model import (
    AccountStatus,
    PropProfileVersion,
    RiskPolicyVersion,
    TradingAccount,
)
from traderx.identity.authorization import Actor, Role
from traderx.integrations.broker_model import BrokerIntegrationProfile, BrokerProvider
from traderx.integrations.broker_service import (
    begin_managed_mt5_enrollment,
    bind_selected_account,
    discovered_account_payload,
    enroll_managed_mt5_agent,
    ingest_managed_mt5_snapshot,
    managed_mt5_enrollment_configuration,
    remove_managed_mt5_integration,
    renew_managed_mt5_enrollment,
    sync_selected_broker_account,
)
from traderx.integrations.broker_service import test_broker_integration as discover_broker_accounts
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


def _send_mt5_snapshot(session: Session, *, enrollment_token: str, agent_id: UUID) -> str:
    agent_token = enroll_managed_mt5_agent(
        session,
        agent_id,
        enrollment_token=enrollment_token,
        login="123456",
        server="Demo-Server",
        connected=True,
        trading_disabled=True,
        terminal_version="5.0.1",
    )
    ingest_managed_mt5_snapshot(
        session,
        agent_id,
        agent_token=agent_token,
        login="123456",
        server="Demo-Server",
        connected=True,
        trading_disabled=True,
        terminal_version="5.0.1",
        balance="10000.00",
        equity="10005.00",
        currency="USD",
        positions=[],
        deals=[],
        instruments=[],
    )
    return agent_token


def test_managed_mt5_enrollment_hides_bridge_transport_details_and_can_be_renewed() -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        enrollment = begin_managed_mt5_enrollment(
            session,
            actor,
            account_login="123456",
            server="Demo-Server",
        )
        integration = enrollment.integration
        session.commit()

        profile = session.scalar(select(BrokerIntegrationProfile))
        assert integration.provider == BrokerProvider.MT5_TERMINAL_BRIDGE
        assert profile.bridge_url is None
        assert profile.bridge_id == str(enrollment.agent_id)
        assert (
            session.scalars(
                select(CredentialVersion).where(CredentialVersion.integration_id == integration.id)
            ).all()
            == []
        )

        renewed = renew_managed_mt5_enrollment(session, actor, integration)
        assert renewed.agent_id == enrollment.agent_id
        assert renewed.enrollment_token != enrollment.enrollment_token
        assert renewed.account_login == "123456"
        assert renewed.server == "Demo-Server"

        account = TradingAccount(
            name="Primary evaluation",
            mode="DEMO",
            currency="USD",
            starting_balance=Decimal("10000"),
            status=AccountStatus.ACTIVE,
            broker_integration_id=integration.id,
            provider_account_id="123456",
        )
        session.add(account)
        session.flush()
        assert remove_managed_mt5_integration(session, actor, integration) == 1
        assert integration.state == "REMOVED"
        assert account.status == AccountStatus.BLOCKED
        assert account.broker_integration_id is None
        assert account.provider_account_id is None

        reactivated = begin_managed_mt5_enrollment(
            session, actor, account_login="123456", server="Demo-Server"
        )
        assert reactivated.integration.id == integration.id
        assert reactivated.enrollment_token != renewed.enrollment_token
        assert reactivated.integration.state == "DISABLED"
    finally:
        session.close()
        engine.dispose()


def test_managed_mt5_bridge_enrolls_outbound_and_discovers_only_a_verified_snapshot() -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        enrollment = begin_managed_mt5_enrollment(
            session, actor, account_login="123456", server="Demo-Server"
        )
        identity = managed_mt5_enrollment_configuration(
            session, enrollment.agent_id, enrollment_token=enrollment.enrollment_token
        )
        assert identity == {"login": "123456", "server": "Demo-Server"}
        _send_mt5_snapshot(
            session,
            enrollment_token=enrollment.enrollment_token,
            agent_id=enrollment.agent_id,
        )
        candidates = discover_broker_accounts(session, enrollment.integration)
        session.commit()

        assert candidates == [
            {
                "provider_account_id": "123456",
                "display_name": "Demo-Server 123456",
                "currency": "USD",
                "account_mode": "READ_ONLY",
            }
        ]
        assert (
            discovered_account_payload(session, enrollment.integration.id)[0]["verification_status"]
            == "VERIFIED"
        )
    finally:
        session.close()
        engine.dispose()


def test_syncing_a_selected_mt5_account_commits_verified_account_and_risk_snapshot() -> None:
    session, engine = _session()
    try:
        actor = Actor(Role.OWNER, "MFA")
        enrollment = begin_managed_mt5_enrollment(
            session, actor, account_login="123456", server="Demo-Server"
        )
        _send_mt5_snapshot(
            session,
            enrollment_token=enrollment.enrollment_token,
            agent_id=enrollment.agent_id,
        )
        discover_broker_accounts(session, enrollment.integration)
        account = TradingAccount(
            name="Primary",
            mode="DEMO",
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
        bind_selected_account(session, actor, enrollment.integration, "123456")
        account.broker_integration_id = enrollment.integration.id
        account.provider_account_id = "123456"

        result = sync_selected_broker_account(session, enrollment.integration, account)
        session.commit()

        assert result["quality"] == "VERIFIED"
        assert session.scalar(select(AccountSnapshot)).equity == Decimal("10005")
        risk = session.scalar(select(RiskSnapshot))
        assert risk is not None
        assert risk.state == "NORMAL"
        assert risk.capacity == 2
    finally:
        session.close()
        engine.dispose()
