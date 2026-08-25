"""Fetch, normalize, and archive Forex Factory data consistently across runtimes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from adapters.news.forex_factory import fetch_forex_factory_events
from modules.research.forex_factory_archive import (
    ForexFactoryArchive,
    ForexFactoryArchiveReference,
)


async def scrape_and_archive_forex_factory(
    *,
    owner_id: UUID,
    feed_url: str,
    archive: ForexFactoryArchive,
    scraped_at: datetime | None = None,
) -> ForexFactoryArchiveReference:
    observed_at = (scraped_at or datetime.now(UTC)).astimezone(UTC)
    existing = archive.find_covering_date(owner_id, observed_at.date())
    if existing is not None:
        return existing
    events = await fetch_forex_factory_events(feed_url)
    return archive.save_period(
        owner_id=owner_id,
        events=events,
        feed_url=feed_url,
        scraped_at=observed_at,
    )
