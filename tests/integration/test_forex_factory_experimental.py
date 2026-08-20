from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from traderx.economic_calendar.providers import parse_forex_factory_experimental
from traderx.integrations.ports import SourceSemantics
from traderx.market_data.model import EconomicEvent, EventRiskPolicyVersion
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    SourceRole,
    build_source_evidence,
)
from traderx.risk.event_guard import evaluate_event_guard
from traderx.shared.db import Base, load_model_metadata


def test_scraped_forex_factory_event_is_explicitly_experimental() -> None:
    events = parse_forex_factory_experimental(
        payload={
            "results": [
                {
                    "id": "cpi-1",
                    "title": "Consumer Price Index",
                    "datetime": "2026-08-20T12:30:00Z",
                    "impact": "High",
                    "currency": "USD",
                }
            ]
        },
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    assert events[0]["source_origin"] == "SCRAPED_EXPERIMENTAL"
    assert events[0]["canonical_type"] == "US_CPI"


def test_scraped_experimental_event_never_blocks_or_qualifies() -> None:
    load_model_metadata()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    account_id = uuid4()
    with Session(engine) as database:
        database.add(
            EventRiskPolicyVersion(
                account_id=account_id,
                policy_version="v1",
                enabled_event_types=["US_CPI"],
                pre_buffer_minutes=30,
                post_buffer_minutes=30,
                coverage_required=False,
                reason="Guard high impact releases",
                effective_from=now,
            )
        )
        database.add(
            EconomicEvent(
                event_at=now + timedelta(minutes=15),
                scheduled_at=now + timedelta(minutes=15),
                currency_or_region="USD",
                impact="HIGH",
                payload={"title": "CPI"},
                source_provider="FOREX_FACTORY_SCRAPER",
                external_id="cpi-1",
                source_origin="SCRAPED_EXPERIMENTAL",
                source_url="https://www.forexfactory.com/calendar",
                canonical_type="US_CPI",
                affected_categories=["FOREX"],
                status="UPCOMING",
                revision_number=1,
            )
        )
        database.commit()
        assert not evaluate_event_guard(
            database, account_id=account_id, category="FOREX", instrument_id=None, now=now
        ).blocked

    evidence = build_source_evidence(
        provider="FOREX_FACTORY_SCRAPER",
        capability="SCHEDULE",
        semantics=SourceSemantics.SCRAPED_EXPERIMENTAL,
        source_role=SourceRole.SPECIALIST_PRIMARY,
        observed_at=now,
        received_at=now,
        evaluated_at=now,
        policy=FreshnessPolicy(
            provider="FOREX_FACTORY_SCRAPER",
            capability="SCHEDULE",
            version="experimental-v1",
            maximum_age=timedelta(minutes=30),
        ),
        entitlement_status="NOT_REQUIRED",
        complete=True,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
    )
    assert not evidence.qualifies
