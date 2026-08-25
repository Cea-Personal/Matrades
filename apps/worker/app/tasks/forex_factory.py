"""Scheduled Forex Factory scraping with per-account idempotency."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from adapters.news.forex_factory import DEFAULT_FOREX_FACTORY_FEED
from apps.worker.app.celery_app import celery_app
from modules.connections.models import ConnectionProvider
from modules.research.forex_factory_archive import ForexFactoryArchive
from modules.research.forex_factory_service import scrape_and_archive_forex_factory
from modules.research.scheduling import default_schedule, is_due, normalize_schedule
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore


def _fallback_schedule() -> dict[str, object]:
    return default_schedule(
        enabled=settings.forex_factory_schedule_enabled,
        run_at=f"{settings.forex_factory_schedule_hour_utc:02d}:{settings.forex_factory_schedule_minute_utc:02d}",
    )


async def _execute_forex_factory_scrape(run_id: UUID) -> dict[str, object]:
    async with unit_of_work() as session:
        record = await session.get(ResourceRecord, run_id)
        if record is None or record.kind != "forex_factory_scrape":
            raise RuntimeError("Forex Factory scrape run not found")
        connection_id = UUID(str(record.data["connection_id"]))
        connection = await session.get(ResourceRecord, connection_id)
        if connection is None or connection.kind != "connection":
            raise RuntimeError("Forex Factory connection not found")
        feed_url = str(
            connection.data.get("configuration", {}).get("feed_url", DEFAULT_FOREX_FACTORY_FEED)
        )
        await ResourceStore(session).update(
            record,
            {**record.data, "started_at": datetime.now(UTC).isoformat()},
            state="RUNNING",
            event_type="forex_factory_scrape.running",
        )

    try:
        reference = await scrape_and_archive_forex_factory(
            owner_id=record.owner_id,
            feed_url=feed_url,
            archive=ForexFactoryArchive(settings.research_artifact_root),
        )
    except (OSError, httpx.HTTPError, RuntimeError, ValueError) as exc:
        await _mark_failed(run_id, exc)
        raise

    completed_at = datetime.now(UTC)
    details = {
        **record.data,
        "completed_at": completed_at.isoformat(),
        "feed_url": feed_url,
        "period_key": reference.period_key,
        "period_start": reference.period_start.isoformat(),
        "period_end": reference.period_end.isoformat(),
        "event_count": reference.event_count,
        "archive_path": reference.relative_path,
        "skipped": reference.skipped,
        "message": reference.message,
    }
    async with unit_of_work() as session:
        current = await session.get(ResourceRecord, run_id)
        connection = await session.get(ResourceRecord, UUID(str(record.data["connection_id"])))
        if current is None or connection is None:
            raise RuntimeError("Forex Factory scrape run disappeared")
        store = ResourceStore(session)
        await store.update(
            current,
            details,
            state="SKIPPED" if reference.skipped else "COMPLETED",
            event_type=(
                "forex_factory_scrape.skipped"
                if reference.skipped
                else "forex_factory_scrape.completed"
            ),
        )
        checked_at = completed_at.isoformat()
        await store.update(
            connection,
            {
                **connection.data,
                "health": "HEALTHY" if reference.event_count else "STALE",
                "last_checked": (
                    checked_at if not reference.skipped else connection.data.get("last_checked")
                ),
                "last_success": (
                    checked_at if reference.event_count else connection.data.get("last_success")
                ),
                "capabilities": ["news.read", "calendar.read", "forex_factory.scrape"],
                "fresh": bool(reference.event_count),
                "last_error": None,
            },
            event_type=(
                "connection.forex_factory_scrape_skipped"
                if reference.skipped
                else "connection.forex_factory_scraped"
            ),
        )
    return details


@celery_app.task(name="apps.worker.app.tasks.forex_factory.run_forex_factory_scrape")
def run_forex_factory_scrape(run_id: str) -> dict[str, object]:
    return asyncio.run(_execute_forex_factory_scrape(UUID(run_id)))


async def _mark_failed(run_id: UUID, error: Exception) -> None:
    async with unit_of_work() as session:
        record = await session.get(ResourceRecord, run_id)
        if record is None:
            return
        await ResourceStore(session).update(
            record,
            {
                **record.data,
                "completed_at": datetime.now(UTC).isoformat(),
                "failure": type(error).__name__,
                "message": f"Forex Factory scraper failed: {type(error).__name__}",
            },
            state="FAILED",
            event_type="forex_factory_scrape.failed",
        )


async def _create_scheduled_scrapes() -> list[str]:
    now = datetime.now(UTC)
    created: list[str] = []
    fallback = _fallback_schedule()
    async with unit_of_work() as session:
        accounts = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "account",
                        ResourceRecord.state != "DELETED",
                    )
                )
            ).all()
        )
        connections = [
            item
            for item in (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "connection",
                        ResourceRecord.state != "DELETED",
                    )
                )
            ).all()
            if item.data.get("provider") == ConnectionProvider.FOREX_FACTORY.value
            and item.data.get("active", True)
        ]
        existing = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(ResourceRecord.kind == "forex_factory_scrape")
                )
            ).all()
        )
        scheduled_keys = {
            (
                str(item.owner_id),
                str(item.data.get("account_id")),
                str(item.data.get("scheduled_date")),
            )
            for item in existing
            if item.data.get("scheduled_date")
        }
        store = ResourceStore(session)
        for account in accounts:
            if not account.data.get("active", True):
                continue
            connection = next(
                (item for item in connections if item.owner_id == account.owner_id), None
            )
            if connection is None:
                continue
            schedule = normalize_schedule(
                account.data.get("forex_factory_schedule"), fallback=fallback
            )
            if not is_due(schedule, now=now):
                continue
            local_date = now.astimezone(ZoneInfo(str(schedule["timezone"]))).date().isoformat()
            key = (str(account.owner_id), str(account.id), local_date)
            if key in scheduled_keys:
                continue
            record = await store.create(
                "forex_factory_scrape",
                account.owner_id,
                {
                    "account_id": str(account.id),
                    "connection_id": str(connection.id),
                    "scheduled_date": local_date,
                    "scheduled_at": now.isoformat(),
                    "schedule": schedule,
                    "trigger": "SCHEDULED",
                },
                state="QUEUED",
                event_type="forex_factory_scrape.scheduled",
            )
            created.append(str(record.id))
    for run_id in created:
        run_forex_factory_scrape.delay(run_id)
    return created


@celery_app.task(name="apps.worker.app.tasks.forex_factory.schedule_forex_factory_scrapes")
def schedule_forex_factory_scrapes() -> list[str]:
    if not settings.forex_factory_schedule_enabled:
        return []
    return asyncio.run(_create_scheduled_scrapes())
