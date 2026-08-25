"""Durable autonomous research-cycle tasks and daily scheduling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from adapters.market_data.research import LiveResearchDataProvider
from adapters.news.forex_factory import DEFAULT_FOREX_FACTORY_FEED, fetch_forex_factory_events
from apps.worker.app.celery_app import celery_app
from modules.agents.rpc import RedisAgentGateway
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection
from modules.research.artifacts import ResearchCycleArchive
from modules.research.models import MarketCategory, TypedResearchRun
from modules.research.scheduling import default_schedule, is_due, normalize_schedule
from modules.research.workflow import AutonomousResearchWorkflow
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.domain_types import ResearchLaneKey
from packages.shared.store import ResourceRecord, ResourceStore

DEFAULT_CATEGORIES = [
    MarketCategory.FOREX,
    MarketCategory.METAL,
    MarketCategory.CRYPTO,
]


async def _execute_research_cycle(run_id: UUID) -> dict:
    typed_lanes: list[ResearchLaneKey] | None = None
    typed_matrix_version = 1
    async with unit_of_work() as session:
        record = await session.get(ResourceRecord, run_id)
        if record is None or record.kind != "research_run":
            raise RuntimeError("research run not found")
        await ResourceStore(session).update(
            record,
            {**record.data, "started_at": datetime.now(UTC).isoformat()},
            state="RESEARCHING",
            event_type="research.researching",
        )
        categories = [
            MarketCategory(value)
            for value in record.data.get(
                "market_categories", [item.value for item in DEFAULT_CATEGORIES]
            )
        ]
        if record.data.get("lanes"):
            typed_lanes = [ResearchLaneKey.model_validate(item) for item in record.data["lanes"]]
            typed_matrix_version = int(record.data.get("matrix_version", 1))
        owner_id = record.owner_id
        twelve = await find_connection(session, owner_id, ConnectionProvider.TWELVE_DATA)
        coinbase = await find_connection(session, owner_id, ConnectionProvider.COINBASE)
        forex_factory = await find_connection(session, owner_id, ConnectionProvider.FOREX_FACTORY)
        custom_news = await find_connection(session, owner_id, ConnectionProvider.NEWS)

    enabled = {
        provider_name
        for provider_name, resolved in (
            (ConnectionProvider.TWELVE_DATA, twelve),
            (ConnectionProvider.COINBASE, coinbase),
        )
        if resolved is not None
    }
    twelve_configuration = twelve.profile.configuration if twelve else {}
    coinbase_configuration = coinbase.profile.configuration if coinbase else {}
    provider = LiveResearchDataProvider(
        settings,
        twelve_data_api_key=twelve.secret if twelve else None,
        enabled_providers=enabled,
        forex_universe=twelve_configuration.get("forex_universe"),
        metals_universe=twelve_configuration.get("metals_universe"),
        crypto_universe=coinbase_configuration.get("crypto_universe"),
    )
    agents = RedisAgentGateway(
        settings.redis_url,
        timeout_seconds=settings.research_agent_timeout_seconds,
    )
    try:
        workflow = AutonomousResearchWorkflow(provider, agents)
        if typed_lanes:
            typed_run = TypedResearchRun(
                owner_id=owner_id,
                account_id=UUID(str(record.data["account_id"])),
                matrix_version=typed_matrix_version,
                requested_lanes=typed_lanes,
                created_at=datetime.now(UTC),
            )
            typed_result = await workflow.run_matrix(typed_run)
            serialized = typed_result.model_dump(mode="json")
            serialized["lane_results"] = [
                item.model_dump(mode="json") for item in typed_result.lane_results
            ]
            serialized["status"] = typed_result.state
            artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
                owner_id=owner_id,
                cycle_type="market_research",
                cycle_id=run_id,
                occurred_at=typed_result.created_at,
                details=serialized,
            )
            serialized["artifact"] = {
                "relative_path": artifact.relative_path,
                "checksum": artifact.checksum,
                "manifest_name": artifact.manifest_name,
            }
            async with unit_of_work() as typed_session:
                typed_record = await typed_session.get(ResourceRecord, run_id)
                if typed_record is None:
                    raise RuntimeError("research run disappeared")
                await ResourceStore(typed_session).update(
                    typed_record,
                    {**typed_record.data, **serialized},
                    state=typed_result.state,
                    event_type=f"research.{typed_result.state.lower()}",
                )
            return serialized
        result = await workflow.run(categories)
    finally:
        await provider.close()
        await agents.close()

    serialized = result.model_dump(mode="json")
    news_connection = forex_factory or custom_news
    news_source: dict[str, object] = {
        "provider": (
            ConnectionProvider.FOREX_FACTORY.value
            if forex_factory
            else ConnectionProvider.NEWS.value
            if custom_news
            else None
        ),
        "configured": news_connection is not None,
        "status": "NOT_CONFIGURED" if news_connection is None else "CONFIGURED",
    }
    news_events: list[dict[str, object]] = []
    if forex_factory:
        feed_url = str(
            forex_factory.profile.configuration.get("feed_url", DEFAULT_FOREX_FACTORY_FEED)
        )
        news_source["feed_url"] = feed_url
        try:
            news_events = [
                event.model_dump(mode="json")
                for event in await fetch_forex_factory_events(feed_url)
            ]
            news_source["status"] = "HEALTHY" if news_events else "STALE"
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            news_source["status"] = "OFFLINE"
            news_source["error"] = type(exc).__name__
    elif custom_news:
        news_source["endpoint"] = custom_news.profile.configuration.get("base_url")
        news_source["status"] = "EXTERNAL_CUSTOM_PROVIDER"
    serialized["news_source"] = news_source
    serialized["news_events"] = news_events
    artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
        owner_id=owner_id,
        cycle_type="market_research",
        cycle_id=run_id,
        occurred_at=result.completed_at,
        details=serialized,
    )
    serialized["artifact"] = {
        "relative_path": artifact.relative_path,
        "checksum": artifact.checksum,
        "manifest_name": artifact.manifest_name,
    }
    async with unit_of_work() as session:
        record = await session.get(ResourceRecord, run_id)
        if record is None:
            raise RuntimeError("research run disappeared")
        await ResourceStore(session).update(
            record,
            {**record.data, **serialized},
            state=result.state,
            event_type=f"research.{result.state.lower()}",
            evidence={
                "candidate_count": len(result.candidates),
                "missing_categories": [item.value for item in result.missing_categories],
            },
        )
    return serialized


@celery_app.task(name="apps.worker.app.tasks.research.run_research_cycle")
def run_research_cycle(run_id: str) -> dict:
    """Run provider discovery and agent review for an already-persisted run."""
    parsed_id = UUID(run_id)
    try:
        return asyncio.run(_execute_research_cycle(parsed_id))
    except Exception as exc:
        asyncio.run(_mark_failed(parsed_id, exc))
        raise


async def _mark_failed(run_id: UUID, error: Exception) -> None:
    async with unit_of_work() as session:
        record = await session.get(ResourceRecord, run_id)
        if record is None or record.kind != "research_run":
            return
        completed_at = datetime.now(UTC)
        details = {
            "state": "FAILED",
            "completed_at": completed_at.isoformat(),
            "failure": type(error).__name__,
        }
        artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
            owner_id=record.owner_id,
            cycle_type="market_research",
            cycle_id=run_id,
            occurred_at=completed_at,
            details=details,
        )
        artifact_data = {
            "relative_path": artifact.relative_path,
            "checksum": artifact.checksum,
            "manifest_name": artifact.manifest_name,
        }
        await ResourceStore(session).update(
            record,
            {
                **record.data,
                **details,
                "artifact": artifact_data,
            },
            state="FAILED",
            event_type="research.failed",
            evidence={"failure_type": type(error).__name__},
        )


async def _create_scheduled_runs() -> list[str]:
    now = datetime.now(UTC)
    created: list[str] = []
    fallback_schedule = default_schedule(
        enabled=settings.research_schedule_enabled,
        run_at=f"{settings.research_schedule_hour_utc:02d}:{settings.research_schedule_minute_utc:02d}",
    )
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
        existing = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(ResourceRecord.kind == "research_run")
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
            schedule = normalize_schedule(
                account.data.get("research_schedule"), fallback=fallback_schedule
            )
            if not is_due(schedule, now=now):
                continue
            local_date = now.astimezone(ZoneInfo(schedule["timezone"])).date().isoformat()
            key = (str(account.owner_id), str(account.id), local_date)
            if key in scheduled_keys:
                continue
            record = await store.create(
                "research_run",
                account.owner_id,
                {
                    "account_id": str(account.id),
                    "market_categories": [item.value for item in DEFAULT_CATEGORIES],
                    "scheduled_date": local_date,
                    "scheduled_at": now.isoformat(),
                    "research_schedule": schedule,
                    "trigger": "SCHEDULED",
                    "candidates": [],
                    "missing_categories": [],
                    "degraded_reasons": [],
                },
                state="QUEUED",
                event_type="research.scheduled",
            )
            created.append(str(record.id))
    for run_id in created:
        run_research_cycle.delay(run_id)
    return created


@celery_app.task(name="apps.worker.app.tasks.research.schedule_research_cycles")
def schedule_research_cycles() -> list[str]:
    """Idempotently enqueue one daily research cycle for each configured account."""
    if not settings.research_schedule_enabled:
        return []
    return asyncio.run(_create_scheduled_runs())
