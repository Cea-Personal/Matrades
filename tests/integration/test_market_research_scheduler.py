from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.market_research.model import MarketResearchSchedule
from traderx.market_research.scheduling import claim_occurrence, next_due_at
from traderx.shared.db import Base, load_model_metadata


def test_anchored_schedule_preserves_local_wall_time_across_dst_and_rejects_bounds() -> None:
    anchor = datetime.fromisoformat("2026-03-07T09:00:00-05:00")
    due = next_due_at(
        anchored_start_local=anchor,
        account_timezone="America/New_York",
        interval_seconds=86400,
        after=datetime(2026, 3, 7, 15, 0, tzinfo=UTC),
    )
    assert due == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)

    for invalid in (3599, 2592001):
        try:
            next_due_at(
                anchored_start_local=anchor,
                account_timezone="America/New_York",
                interval_seconds=invalid,
                after=datetime(2026, 3, 7, 15, 0, tzinfo=UTC),
            )
        except ValueError as error:
            assert "between one hour and 30 days" in str(error)
        else:
            raise AssertionError("invalid schedule interval was accepted")


def test_due_claim_is_unique_and_records_overlap_without_catch_up() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        account = TradingAccount(
            name="Demo",
            mode="DEMO",
            currency="USD",
            starting_balance=Decimal("10000"),
        )
        database.add(account)
        database.flush()
        schedule = MarketResearchSchedule(
            account_id=account.id,
            interval_seconds=3600,
            anchored_start_local=now,
            account_timezone="UTC",
            enabled=True,
            next_run_at=now,
            changed_by=uuid4(),
            change_reason="Run hourly market research",
        )
        database.add(schedule)
        database.flush()

        first = claim_occurrence(database, schedule, scheduled_for=now, claimed_at=now)
        duplicate = claim_occurrence(database, schedule, scheduled_for=now, claimed_at=now)
        assert first.id == duplicate.id
        assert first.state == "CLAIMED"

        overlap = claim_occurrence(
            database,
            schedule,
            scheduled_for=now + timedelta(hours=1),
            claimed_at=now + timedelta(hours=1),
            active_run_id=uuid4(),
        )
        assert overlap.state == "SKIPPED_OVERLAP"
        assert overlap.reason == "PREVIOUS_COORDINATED_RUN_ACTIVE"
        assert schedule.next_run_at == now + timedelta(hours=2)
