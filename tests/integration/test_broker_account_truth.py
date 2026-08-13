from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.integrations.broker_model import (
    BrokerDiscoveredAccount,
    BrokerIntegrationProfile,
    BrokerProvider,
    BrokerReconciliationCheckpoint,
)
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.integrations.reconciliation import (
    NormalizedBrokerSnapshot,
    commit_authoritative_snapshot,
    record_broker_failure,
)
from traderx.risk.model import AccountSnapshot, CircuitBreaker
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


def _fixtures(session: Session) -> tuple[Integration, TradingAccount]:
    integration = Integration(
        name="MT5 Demo-Server 123456",
        provider=BrokerProvider.MT5_TERMINAL_BRIDGE,
        state="DISABLED",
        capabilities=["ACCOUNT_READ", "POSITION_READ", "DEAL_READ", "INSTRUMENT_READ"],
    )
    account = TradingAccount(
        name="Primary",
        mode="LIVE",
        currency="USD",
        starting_balance=Decimal("10000"),
        status=AccountStatus.DRAFT,
    )
    session.add_all([integration, account])
    session.flush()
    session.add(
        BrokerIntegrationProfile(
            integration_id=integration.id,
            provider=BrokerProvider.MT5_TERMINAL_BRIDGE,
            account_login="123456",
            server="Demo-Server",
            selected_provider_account_id="123456",
            configuration={},
        )
    )
    session.add(
        BrokerDiscoveredAccount(
            integration_id=integration.id,
            provider_account_id="123456",
            display_name="Demo-Server 123456",
            currency="USD",
            account_mode="DEMO",
            verification_status="VERIFIED",
            verified_at=datetime(2026, 8, 13, tzinfo=UTC),
        )
    )
    session.commit()
    return integration, account


def _truth() -> NormalizedBrokerSnapshot:
    return NormalizedBrokerSnapshot(
        provider_account_id="123456",
        provider_event_id="mt5-73",
        balance=Decimal("10000.00"),
        equity=Decimal("10020.50"),
        realized_pl=Decimal("20.50"),
        floating_pl=Decimal("5.50"),
        observed_at=datetime(2026, 8, 13, tzinfo=UTC),
        source_cursor=None,
        source_window={"lookback_days": 2},
        raw_evidence={"provider": "MT5_TERMINAL_BRIDGE"},
        open_position_count=1,
    )


def test_authoritative_snapshot_and_checkpoint_commit_together() -> None:
    session, engine = _session()
    try:
        integration, account = _fixtures(session)
        snapshot = commit_authoritative_snapshot(session, integration, account, _truth())
        session.commit()

        assert snapshot.quality == "VERIFIED"
        assert session.scalar(select(AccountSnapshot).where(AccountSnapshot.id == snapshot.id)) is not None
        checkpoint = session.scalar(select(BrokerReconciliationCheckpoint))
        assert checkpoint is not None
        assert checkpoint.account_snapshot_id == snapshot.id
        assert checkpoint.source_cursor is None
        assert session.get(TradingAccount, account.id).status == AccountStatus.ACTIVE
        assert session.get(Integration, integration.id).state == "HEALTHY"
        assert session.scalar(select(IntegrationHealthObservation)).status == "HEALTHY"
    finally:
        session.close()
        engine.dispose()


def test_failed_reconciliation_keeps_last_good_snapshot_and_blocks_account() -> None:
    session, engine = _session()
    try:
        integration, account = _fixtures(session)
        good = commit_authoritative_snapshot(session, integration, account, _truth())
        session.commit()

        record_broker_failure(
            session,
            integration,
            account,
            reason_code="STALE_PROVIDER_SNAPSHOT",
            detail="snapshot exceeded the configured freshness objective",
        )
        session.commit()

        snapshots = session.scalars(select(AccountSnapshot).order_by(AccountSnapshot.created_at)).all()
        assert [snapshot.id for snapshot in snapshots] == [good.id]
        assert session.get(TradingAccount, account.id).status == AccountStatus.BLOCKED
        assert session.get(Integration, integration.id).state == "DEGRADED"
        breaker = session.scalar(select(CircuitBreaker))
        assert breaker is not None
        assert breaker.state == "TRIPPED"
        assert breaker.trigger_evidence["reason_code"] == "STALE_PROVIDER_SNAPSHOT"
    finally:
        session.close()
        engine.dispose()
