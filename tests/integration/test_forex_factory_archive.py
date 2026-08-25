from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from modules.analysis.models import EconomicEvent
from modules.research.forex_factory_archive import ForexFactoryArchive


def test_period_archive_uses_covered_dates_and_skips_duplicates(tmp_path) -> None:
    archive = ForexFactoryArchive(tmp_path)
    owner_id = uuid4()
    events = [
        EconomicEvent(
            name="Event A",
            currency="USD",
            impact="HIGH",
            scheduled_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
            source="FOREX_FACTORY",
        ),
        EconomicEvent(
            name="Event B",
            currency="EUR",
            impact="MEDIUM",
            scheduled_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
            source="FOREX_FACTORY",
        ),
    ]
    first = archive.save_period(
        owner_id=owner_id,
        events=events,
        feed_url="https://example.test/calendar.json",
        scraped_at=datetime(2026, 8, 25, 8, tzinfo=UTC),
    )
    second = archive.save_period(
        owner_id=owner_id,
        events=events,
        feed_url="https://example.test/calendar.json",
        scraped_at=datetime(2026, 8, 25, 9, tzinfo=UTC),
    )

    assert first.period_key == "2429-08-2026"
    assert first.relative_path.endswith("/forex_factory/2429-08-2026.json")
    assert not first.skipped
    assert second.skipped
    assert second.message == "Data already exists for period 2429-08-2026; scraper skipped."
    assert archive.find_covering_date(owner_id, datetime(2026, 8, 26, tzinfo=UTC).date())
