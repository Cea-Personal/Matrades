"""Idempotent calendar synchronization tasks.

The ForexFactory task is intentionally excluded from beat and routed to a
dedicated opt-in worker. It is not an official-source task.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
from celery import shared_task
from sqlalchemy import select

from traderx.economic_calendar.providers import (
    BEA,
    BLS,
    FOREX_FACTORY_EXPERIMENTAL_URL,
    owner_cited_source,
    parse_forex_factory_experimental,
    parse_ics_schedule,
)
from traderx.economic_calendar.service import sync_events
from traderx.market_data.model import CalendarCoverage
from traderx.shared.config import get_settings
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.economic_calendar.sync_schedule", acks_late=True)
def synchronize_schedule(provider: str) -> dict[str, object]:
    source = {"BLS": BLS, "BEA": BEA}.get(provider.upper())
    if source is None or source.schedule_url is None:
        if provider.upper() != "FEDERAL_RESERVE":
            return {"provider": provider, "status": "OWNER_CITED_SCHEDULE_REQUIRED"}
        source = owner_cited_source("FEDERAL_RESERVE")
        now = datetime.now(UTC)
        with session_factory().begin() as database:
            existing = database.scalar(
                select(CalendarCoverage).where(
                    CalendarCoverage.source_provider == source.provider,
                    CalendarCoverage.scope_key == "GLOBAL",
                )
            )
            if existing and existing.status == "VERIFIED" and existing.covered_through and existing.covered_through >= now:
                return {"provider": source.provider, "status": "VERIFIED"}
            _coverage(
                database, source.provider, "GLOBAL", "OWNER_CITED_REQUIRED",
                str(source.schedule_url), now, 0,
                "Federal Reserve does not expose a documented machine-readable FOMC calendar feed",
            )
        return {"provider": source.provider, "status": "OWNER_CITED_SCHEDULE_REQUIRED"}
    now = datetime.now(UTC)
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.get(source.schedule_url, headers={"Accept": "text/calendar"})
            response.raise_for_status()
        events = parse_ics_schedule(provider=source.provider, content=response.content, retrieved_at=now)
        with session_factory().begin() as database:
            sync_events(database, events=events, source_url=source.schedule_url, now=now)
            _coverage(database, source.provider, "GLOBAL", "VERIFIED", source.schedule_url, now, len(events))
        return {"provider": source.provider, "status": "VERIFIED", "events": len(events)}
    except (httpx.HTTPError, ValueError) as error:
        with session_factory().begin() as database:
            _coverage(database, source.provider, "GLOBAL", "COVERAGE_DEGRADED", source.schedule_url, now, 0, str(error))
        return {"provider": source.provider, "status": "COVERAGE_DEGRADED"}


@shared_task(name="traderx.economic_calendar.sync_forex_factory_experimental", acks_late=True)
def synchronize_forex_factory_experimental(
    *, start_date: str, end_date: str, sources: list[str], limit: int, offset: int
) -> dict[str, object]:
    """Fetch the local experimental sidecar; it never updates calendar coverage."""

    settings = get_settings()
    if settings.environment == "production" or not settings.experimental_calendar_scraper_enabled:
        return {"provider": "FOREX_FACTORY_SCRAPER", "status": "DISABLED_NON_PRODUCTION_ONLY"}
    now = datetime.now(UTC)
    try:
        first_day = date.fromisoformat(start_date)
        last_day = date.fromisoformat(end_date)
        if last_day < first_day or (last_day - first_day).days > 31:
            raise ValueError("experimental import date range is invalid")
        requested_sources = tuple(sources or ["forex"])
        if any(source not in {"forex", "cryptocraft", "energyexch", "metalsmine"} for source in requested_sources):
            raise ValueError("experimental import contains an unsupported source")
        if not 1 <= limit <= 500 or not 0 <= offset <= 10000:
            raise ValueError("experimental import page controls are invalid")
        imported: list[dict[str, object]] = []
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            current_day = first_day
            while current_day <= last_day:
                for source in requested_sources:
                    response = client.get(
                        f"http://forex-factory-scraper:5000/api/{source}/daily",
                        params={
                            "day": current_day.day,
                            "month": current_day.month,
                            "year": current_day.year,
                            "limit": limit,
                            "offset": offset,
                        },
                    )
                    response.raise_for_status()
                    for event in parse_forex_factory_experimental(
                        payload=response.json(), retrieved_at=now
                    ):
                        event["external_id"] = f"{source}:{event['external_id']}"
                        imported.append(event)
                current_day += timedelta(days=1)
        with session_factory().begin() as database:
            sync_events(
                database,
                events=imported,
                source_url=FOREX_FACTORY_EXPERIMENTAL_URL,
                now=now,
            )
        return {
            "provider": "FOREX_FACTORY_SCRAPER",
            "status": "IMPORTED_EXPERIMENTAL_NOT_FOR_GATING",
            "events": len(imported),
            "start_date": start_date,
            "end_date": end_date,
            "sources": list(requested_sources),
            "limit": limit,
            "offset": offset,
        }
    except (httpx.HTTPError, ValueError) as error:
        return {
            "provider": "FOREX_FACTORY_SCRAPER",
            "status": "EXPERIMENTAL_IMPORT_FAILED",
            "detail": str(error),
        }


def _coverage(database: object, provider: str, scope: str, status: str, source_url: str, now: datetime, count: int, error: str | None = None) -> None:
    row = database.scalar(select(CalendarCoverage).where(CalendarCoverage.source_provider == provider, CalendarCoverage.scope_key == scope))  # type: ignore[attr-defined]
    evidence = {"event_count": count, "error": error}
    if row is None:
        database.add(CalendarCoverage(source_provider=provider, scope_key=scope, status=status, covered_through=now + timedelta(days=14) if status == "VERIFIED" else None, last_success_at=now if status == "VERIFIED" else None, source_url=source_url, evidence=evidence))  # type: ignore[attr-defined]
    else:
        row.status, row.source_url, row.evidence = status, source_url, evidence
        if status == "VERIFIED":
            row.covered_through, row.last_success_at = now + timedelta(days=14), now
