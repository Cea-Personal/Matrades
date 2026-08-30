from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from apps.worker.app.celery_app import celery_app
from modules.knowledge.youtube_ingestion import ingest_youtube_discovery
from modules.research.scheduling import default_schedule, is_due, normalize_schedule
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore


@celery_app.task(name="apps.worker.app.tasks.knowledge.run_youtube_discovery")
def run_youtube_discovery(run_id: str) -> dict[str, object]:
    return asyncio.run(_run_youtube_discovery(UUID(run_id)))


async def _run_youtube_discovery(run_id: UUID) -> dict[str, object]:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        if run is None or run.kind != "youtube_discovery_run":
            raise ValueError("YouTube discovery run not found")
        store = ResourceStore(session)
        requested_at = datetime.now(UTC).isoformat()
        await store.update(
            run,
            {**run.data, "provider_requested_at": requested_at},
            state="RUNNING",
            event_type="knowledge_youtube_discovery.provider_requested",
        )
        try:
            result = await ingest_youtube_discovery(
                session,
                run.owner_id,
                query=str(run.data["query"]),
                limit=int(run.data.get("limit", 5)),
                languages=list(run.data.get("languages", ["en"])),
                category=str(run.data.get("category", "trading")),
            )
        except Exception as exc:
            await store.update(
                run,
                {
                    **run.data,
                    "provider_requested_at": requested_at,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                },
                state="FAILED",
                event_type="knowledge_youtube_discovery.failed",
            )
            return {"run_id": str(run.id), "state": "FAILED"}
        completed_at = datetime.now(UTC).isoformat()
        await store.update(
            run,
            {
                **run.data,
                **result,
                "provider_requested_at": requested_at,
                "completed_at": completed_at,
            },
            state="SUCCEEDED",
            event_type="knowledge_youtube_discovery.completed",
        )
        return {"run_id": str(run.id), "state": "SUCCEEDED"}


async def _create_scheduled_youtube_runs() -> list[str]:
    now = datetime.now(UTC)
    created: list[str] = []
    async with unit_of_work() as session:
        schedules = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "youtube_discovery_schedule",
                        ResourceRecord.state != "DELETED",
                    )
                )
            ).all()
        )
        existing = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "youtube_discovery_run"
                    )
                )
            ).all()
        )
        scheduled_keys = {
            (str(item.owner_id), str(item.data.get("scheduled_date")))
            for item in existing
            if item.data.get("scheduled_date")
        }
        store = ResourceStore(session)
        for record in schedules:
            schedule = normalize_schedule(
                record.data, fallback=default_schedule(enabled=False, run_at="05:00")
            )
            if not is_due(schedule, now=now):
                continue
            local_date = now.astimezone(ZoneInfo(str(schedule["timezone"]))).date().isoformat()
            key = (str(record.owner_id), local_date)
            if key in scheduled_keys:
                continue
            run = await store.create(
                "youtube_discovery_run",
                record.owner_id,
                {
                    "query": record.data.get("query", "trading strategy"),
                    "limit": int(record.data.get("limit", 5)),
                    "languages": record.data.get("languages", ["en"]),
                    "category": record.data.get("category", "trading"),
                    "trigger": "SCHEDULED",
                    "provider": "SERPAPI",
                    "scheduled_date": local_date,
                    "scheduled_at": now.isoformat(),
                    "schedule_id": str(record.id),
                },
                state="QUEUED",
                event_type="knowledge_youtube_discovery.scheduled",
            )
            created.append(str(run.id))
    for run_id in created:
        run_youtube_discovery.delay(run_id)
    return created


@celery_app.task(name="apps.worker.app.tasks.knowledge.schedule_youtube_discoveries")
def schedule_youtube_discoveries() -> list[str]:
    return asyncio.run(_create_scheduled_youtube_runs())
