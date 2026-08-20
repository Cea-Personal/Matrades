from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from traderx.market_data.model import EconomicEvent, EventRiskPolicyVersion
from traderx.risk.event_guard import evaluate_event_guard
from traderx.shared.db import Base, load_model_metadata


def test_high_impact_event_blocks_only_in_configured_window() -> None:
    load_model_metadata(); engine = create_engine("sqlite://") ; Base.metadata.create_all(engine)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    account_id = uuid4()
    with Session(engine) as database:
        database.add(EventRiskPolicyVersion(account_id=account_id, policy_version="v1", enabled_event_types=["US_CPI"], pre_buffer_minutes=30, post_buffer_minutes=30, coverage_required=False, reason="Guard high impact releases", effective_from=now))
        database.add(EconomicEvent(event_at=now + timedelta(minutes=15), scheduled_at=now + timedelta(minutes=15), currency_or_region="USD", impact="HIGH", payload={"title": "CPI"}, source_provider="BLS", external_id="cpi-1", source_origin="OFFICIAL_MACHINE", source_url="https://www.bls.gov/schedule/news_release/bls.ics", canonical_type="US_CPI", affected_categories=["FOREX"], status="UPCOMING", revision_number=1))
        database.commit()
        assert evaluate_event_guard(database, account_id=account_id, category="FOREX", instrument_id=None, now=now).blocked
        assert not evaluate_event_guard(database, account_id=account_id, category="CRYPTO", instrument_id=None, now=now).blocked
