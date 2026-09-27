"""Replayable bounded research imports; no broker or exchange order methods."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from apps.worker.app.celery_app import celery_app
from modules.connections.resolution import resolve_connection
from modules.market_data.research_history import (
    archived_history,
    cached_history,
    persist_dataset,
    persist_features,
    verified_import_binding,
)
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore


async def _ingest(run_id: UUID):
    async with unit_of_work() as db:
        record = await db.get(ResourceRecord, run_id, with_for_update=True)
        if record is None or record.kind != "research_data_import":
            raise ValueError("history import not found")
        if record.state != "QUEUED":
            return {"state": record.state}
        owner, data = record.owner_id, dict(record.data)
        connection = await resolve_connection(db, owner, UUID(data["connection_id"]))
        account = await ResourceStore(db).get("account", UUID(data["account_id"]), owner)
        if account is None or account.state == "DELETED":
            raise ValueError("research account is no longer available")
        bindings = await ResourceStore(db).list("provider_binding", owner)
        if not verified_import_binding(
            bindings, data["account_id"], data["connection_id"], connection.profile.provider
        ):
            raise ValueError("research history binding is no longer verified")
        cached = await cached_history(
            db,
            owner,
            UUID(data["account_id"]),
            connection,
            data["instrument"],
            datetime.fromisoformat(data["start_at"]),
            datetime.fromisoformat(data["end_at"]),
            data["timeframe"],
        )
        await ResourceStore(db).update(
            record,
            {**data, "started_at": datetime.now(UTC).isoformat()},
            state="INGESTING",
            event_type="research_data.import_started",
        )
    candles, source = cached or await archived_history(
        connection,
        owner,
        data["instrument"],
        datetime.fromisoformat(data["start_at"]),
        datetime.fromisoformat(data["end_at"]),
        data["timeframe"],
        account_id=UUID(data["account_id"]),
    )
    async with unit_of_work() as db:
        dataset = await persist_dataset(
            db,
            owner,
            UUID(data["account_id"]),
            connection.id,
            data["instrument"],
            data["timeframe"],
            candles,
            source,
        )
        features = await persist_features(db, owner, dataset, candles, data["timeframe"])
        record = await ResourceStore(db).get("research_data_import", run_id, owner)
        if record is None:
            raise ValueError("history import not found")
        await ResourceStore(db).update(
            record,
            {
                **record.data,
                **dataset,
                "features": features,
                "completed_at": datetime.now(UTC).isoformat(),
            },
            state="COMPLETED",
            event_type="research_data.import_completed",
        )
    return {"state": "COMPLETED", **dataset}


async def _failed(run_id: UUID, error: Exception):
    async with unit_of_work() as db:
        record = await db.get(ResourceRecord, run_id)
        if record is not None and record.kind == "research_data_import":
            await ResourceStore(db).update(
                record,
                {**record.data, "error_type": type(error).__name__},
                state="FAILED",
                event_type="research_data.import_failed",
            )


@celery_app.task(
    name="apps.worker.app.tasks.research_data.ingest_research_history",
    soft_time_limit=1200,
    time_limit=1260,
)
def ingest_research_history(run_id: str):
    try:
        return asyncio.run(_ingest(UUID(run_id)))
    except Exception as error:
        asyncio.run(_failed(UUID(run_id), error))
        raise


async def _recover() -> dict[str, int]:
    async with unit_of_work() as db:
        records = list(
            (
                await db.scalars(
                    select(ResourceRecord)
                    .where(
                        ResourceRecord.kind == "research_data_import",
                        ResourceRecord.state.in_(["QUEUED", "INGESTING"]),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for record in records:
            if record.state == "INGESTING":
                if datetime.fromisoformat(record.data["started_at"]) > datetime.now(
                    UTC
                ) - timedelta(minutes=25):
                    continue
                await ResourceStore(db).update(
                    record, state="QUEUED", event_type="research_data.import_recovered"
                )
            ingest_research_history.apply_async(args=[str(record.id)], countdown=1)
    return {"checked": len(records)}


@celery_app.task(name="apps.worker.app.tasks.research_data.recover_imports")
def recover_imports():
    return asyncio.run(_recover())
