"""Durable autonomous research-cycle tasks and daily scheduling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from adapters.market_data.mt5_research import Mt5ResearchDataProvider
from adapters.market_data.research import LiveResearchDataProvider
from adapters.news.forex_factory import DEFAULT_FOREX_FACTORY_FEED, fetch_forex_factory_events
from apps.worker.app.celery_app import celery_app
from apps.worker.app.tasks.strategies import queue_top_pair_strategies
from modules.agents.rpc import OwnerScopedAgentGateway, RedisAgentGateway
from modules.connections.models import ConnectionProvider, MarketDataCapability, ProviderBinding
from modules.connections.resolution import find_connection, resolve_connection
from modules.research.artifacts import ResearchCycleArchive
from modules.research.matrix import ALL_LANES
from modules.research.models import (
    MarketCategory,
    ResearchLaneResult,
    TypedResearchCandidate,
    TypedResearchRun,
)
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


def _verified_market_bindings(
    records: list[ResourceRecord], account_id: str
) -> list[ProviderBinding]:
    """Validate market bindings without treating economic context as a market lane."""
    return [
        ProviderBinding.model_validate(item.data)
        for item in records
        if item.data.get("account_id") == account_id
        and item.data.get("verification_status") == "VERIFIED"
        and item.data.get("binding_scope", "MARKET_RESEARCH") == "MARKET_RESEARCH"
        and item.data.get("lane") is not None
    ]


def _typed_instrument_data(
    account_id: UUID,
    candidate: TypedResearchCandidate,
    lane_result: ResearchLaneResult,
) -> dict[str, object]:
    """Flatten required authority references while retaining the full typed models."""
    return {
        "account_id": str(account_id),
        "asset_class": candidate.lane.asset_class.value,
        "instrument_type": candidate.lane.instrument_type.value,
        "venue_instrument_id": str(candidate.listing.id),
        "quantity_unit": candidate.specification.quantity_unit.value,
        "listing": candidate.listing.model_dump(mode="json"),
        "specification": candidate.specification.model_dump(mode="json"),
        "specification_version_id": str(candidate.specification.id),
        "connection_binding_id": (
            str(lane_result.binding_id) if lane_result.binding_id else None
        ),
        "source_cut_refs": lane_result.source_cut_refs,
        "freshness": candidate.specification.freshness,
    }


async def _execute_research_cycle(run_id: UUID) -> dict:
    typed_lanes: list[ResearchLaneKey] | None = None
    typed_matrix_version = 1
    configured_lanes: set[str] | None = None
    lane_binding_ids: dict[str, UUID] = {}
    mt5_lane_keys: set[str] = set()
    mt5 = None
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
        if typed_lanes:
            connections = {
                item.id: item
                for item in await ResourceStore(session).list("connection", owner_id)
            }
            bindings = _verified_market_bindings(
                await ResourceStore(session).list("provider_binding", owner_id),
                str(record.data["account_id"]),
            )
            eligible_capabilities = {
                MarketDataCapability.DISCOVERY,
                MarketDataCapability.INSTRUMENT_DIRECTORY,
                MarketDataCapability.QUOTE,
                MarketDataCapability.CANDLES,
                MarketDataCapability.FUTURES_CHAIN,
            }
            configured_lanes = set()
            for binding in bindings:
                connection = connections.get(binding.connection_id)
                if (
                    binding.capability in eligible_capabilities
                    and connection is not None
                    and connection.data.get("health") in {"HEALTHY", "STALE"}
                ):
                    configured_lanes.add(binding.lane.as_string())
                    lane_binding_ids.setdefault(binding.lane.as_string(), binding.id)
                    if (
                        connection.data.get("provider") == ConnectionProvider.MT5_BRIDGE.value
                        and binding.lane.asset_class.value == "METALS"
                        and binding.lane.instrument_type.value == "CFD"
                    ):
                        mt5_lane_keys.add(binding.lane.as_string())
                        if mt5 is None or mt5.id != binding.connection_id:
                            mt5 = await resolve_connection(
                                session, owner_id, binding.connection_id
                            )

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
    lane_providers = {}
    if mt5 and mt5.secret and mt5_lane_keys:
        mt5_provider = Mt5ResearchDataProvider(
            str(mt5.profile.configuration["bridge_url"]),
            mt5.secret,
            UUID(str(record.data["account_id"])),
        )
        lane_providers = {lane_key: mt5_provider for lane_key in mt5_lane_keys}
    provider = LiveResearchDataProvider(
        settings,
        twelve_data_api_key=twelve.secret if twelve else None,
        enabled_providers=enabled,
        forex_universe=twelve_configuration.get("forex_universe"),
        metals_universe=twelve_configuration.get("metals_universe"),
        crypto_universe=coinbase_configuration.get("crypto_universe"),
        configured_lanes=configured_lanes,
        lane_providers=lane_providers,
    )
    agents = OwnerScopedAgentGateway(
        RedisAgentGateway(
            settings.redis_url,
            timeout_seconds=settings.research_agent_timeout_seconds,
        ),
        owner_id,
    )
    try:
        workflow = AutonomousResearchWorkflow(provider, agents)
        if typed_lanes:
            typed_run = TypedResearchRun(
                id=run_id,
                owner_id=owner_id,
                account_id=UUID(str(record.data["account_id"])),
                matrix_version=typed_matrix_version,
                requested_lanes=typed_lanes,
                created_at=datetime.now(UTC),
            )
            typed_result = await workflow.run_matrix(typed_run)
            typed_result = typed_result.model_copy(
                update={
                    "lane_results": [
                        item.model_copy(
                            update={
                                "binding_id": lane_binding_ids.get(item.lane.as_string()),
                            }
                        )
                        for item in typed_result.lane_results
                    ],
                    "source_cut_refs": sorted(
                        {
                            source_cut
                            for item in typed_result.lane_results
                            for source_cut in item.source_cut_refs
                        }
                    ),
                }
            )
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
                typed_store = ResourceStore(typed_session)
                for lane_result in typed_result.lane_results:
                    if lane_result.status.value != "READY" or lane_result.candidate is None:
                        continue
                    candidate = lane_result.candidate
                    instrument_id = uuid5(
                        NAMESPACE_URL,
                        f"instrument:{owner_id}:{candidate.listing.id}:{candidate.specification.id}",
                    )
                    existing_instrument = await typed_store.get(
                        "typed_instrument", instrument_id, owner_id
                    )
                    instrument_data = _typed_instrument_data(
                        typed_run.account_id, candidate, lane_result
                    )
                    if existing_instrument is None:
                        await typed_store.create(
                            "typed_instrument",
                            owner_id,
                            instrument_data,
                            record_id=instrument_id,
                            event_type="research.typed_instrument_persisted",
                        )
                    else:
                        await typed_store.update(
                            existing_instrument,
                            instrument_data,
                            event_type="research.typed_instrument_refreshed",
                        )
                    selection_id = uuid5(
                        NAMESPACE_URL,
                        f"market-selection:{typed_run.id}:{lane_result.lane.as_string()}",
                    )
                    selection = {
                        "research_run_id": str(typed_run.id),
                        "account_id": str(typed_run.account_id),
                        "lane": lane_result.lane.model_dump(mode="json"),
                        "connection_binding_id": (
                            str(lane_result.binding_id) if lane_result.binding_id else None
                        ),
                        "candidate": candidate.model_dump(mode="json"),
                        "ranked_candidates": [
                            item.model_dump(mode="json") for item in lane_result.ranked_candidates
                        ],
                        "source_cut_refs": lane_result.source_cut_refs,
                        "state": "ACTIVE_MARKET_ANALYSIS",
                    }
                    existing_selection = await typed_store.get(
                        "market_selection", selection_id, owner_id
                    )
                    if existing_selection is None:
                        await typed_store.create(
                            "market_selection",
                            owner_id,
                            selection,
                            state="ACTIVE_MARKET_ANALYSIS",
                            record_id=selection_id,
                            event_type="research.candidate_progressed",
                        )
                    else:
                        await typed_store.update(
                            existing_selection,
                            selection,
                            state="ACTIVE_MARKET_ANALYSIS",
                            event_type="research.candidate_refreshed",
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
        result = asyncio.run(_execute_research_cycle(parsed_id))
    except Exception as exc:
        asyncio.run(_mark_failed(parsed_id, exc))
        raise
    # Market evidence is committed before downstream jobs are dispatched.
    # The periodic dispatcher also recovers a broker outage at this boundary.
    queue_top_pair_strategies.delay(run_id)
    return result


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
            matrices = [
                item
                for item in await store.list("research_matrix", account.owner_id)
                if item.data.get("account_id") == str(account.id)
            ]
            matrix = matrices[0] if matrices else None
            schedule = normalize_schedule(
                account.data.get("research_schedule")
                or (matrix.data.get("schedule") if matrix else None),
                fallback=fallback_schedule,
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
                    "matrix_version": int(matrix.data.get("version", 1)) if matrix else 1,
                    "lanes": [
                        item
                        for item in (
                            matrix.data.get("lanes")
                            if matrix
                            else [lane.model_dump(mode="json") for lane in ALL_LANES]
                        )
                        if item.get("enabled", True)
                    ],
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
