from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_research.eligibility import EligibilityInputs
from traderx.market_research.service import ResearchCandidate, rank_candidates
from traderx.notifications.router import route
from traderx.risk.manager import authorize
from traderx.shared.db import Base, load_model_metadata
from traderx.shared.types import RiskState
from traderx_api.routes.dashboard import _dashboard_projections
from traderx_worker.runtime.jobs import checkpoint


def test_risk_decision_meets_interactive_latency_budget() -> None:
    started = perf_counter()
    for _ in range(1_000):
        authorize(
            requested_risk=Decimal("1"),
            risk_state=RiskState.NORMAL,
            capacity=2,
            exposure_acceptable=True,
            remaining_margin=Decimal("10"),
        )
    assert perf_counter() - started < 1


def test_dashboard_and_broker_visibility_scale_to_large_operational_dataset() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, tzinfo=UTC)
    try:
        with factory.begin() as database:
            for index in range(500):
                integration = Integration(
                    name=f"visibility-{index}",
                    category="NOTIFICATION",
                    provider="WEB_INBOX",
                    state="HEALTHY",
                    capabilities=["NOTIFICATION_SEND"],
                    configuration={},
                    official_source=True,
                )
                database.add(integration)
                database.flush()
                database.add(
                    IntegrationHealthObservation(
                        integration_id=integration.id,
                        status="HEALTHY",
                        evidence={"latency_ms": index % 10},
                        observed_at=now,
                    )
                )
        with factory() as database:
            started = perf_counter()
            projection = _dashboard_projections(database, None)
            elapsed = perf_counter() - started
            assert len(projection["integration_health"]) == 500
            assert elapsed < 2
    finally:
        engine.dispose()


def test_large_market_ranking_notifications_and_job_progress_meet_worker_budgets() -> None:
    eligible = EligibilityInputs(
        True,
        True,
        Decimal("100"),
        Decimal("1"),
        Decimal("100"),
        True,
        True,
        True,
        True,
    )
    candidates = [
        ResearchCandidate(
            str(index),
            eligible,
            Decimal(index % 100) / Decimal("100"),
            Decimal("0.8"),
            Decimal("0.9"),
        )
        for index in range(5_000)
    ]
    started = perf_counter()
    ranked = rank_candidates(
        candidates,
        {"volatility": Decimal("0.5"), "liquidity": Decimal("0.35"), "cost": Decimal("0.15")},
    )
    assert len(ranked) == 5_000
    assert perf_counter() - started < 2

    started = perf_counter()
    for _ in range(10_000):
        assert route(severity="CRITICAL", enabled_channels={"EMAIL"}).persist_web_inbox
    job = BackgroundJob(
        id=uuid4(),
        job_type="performance",
        state=JobState.RUNNING,
        context={},
        input_manifest={},
        progress={},
    )
    now = datetime(2026, 8, 14, tzinfo=UTC)
    for completed in range(10_000):
        checkpoint(job, completed=completed, total=10_000, message="progress", now=now)
    assert job.progress["completed_units"] == 9_999
    assert perf_counter() - started < 2
