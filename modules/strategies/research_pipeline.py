"""Pin one strategy research job to each selected market in a completed cycle."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.connections.resolution import ResolvedConnection, find_connection, resolve_connection
from modules.strategies.evidence import resolve_approved_candidate
from packages.shared.config import settings
from packages.shared.store import ResourceRecord, ResourceStore


async def resolve_strategy_basis(
    db: AsyncSession, owner_id: UUID, selection_id: UUID | None = None
) -> dict[str, str]:
    store = ResourceStore(db)
    selections = [
        item
        for item in await store.list("market_selection", owner_id)
        if item.state == "ACTIVE_MARKET_ANALYSIS"
        and (selection_id is None or item.id == selection_id)
    ]
    if not selections:
        raise ValueError("a fresh typed autonomous market research lane is required")
    selection = selections[0]
    research_run = await store.get(
        "research_run", UUID(selection.data["research_run_id"]), owner_id
    )
    if research_run is None:
        raise ValueError("the typed market research run is unavailable")
    candidate = resolve_approved_candidate(
        selection.data,
        research_run.data,
        now=datetime.now(UTC),
        max_age=timedelta(hours=settings.strategy_research_max_market_age_hours),
    )
    source = candidate.fingerprint.source.upper()
    providers = {
        "TWELVE_DATA": ConnectionProvider.TWELVE_DATA,
        "COINBASE": ConnectionProvider.COINBASE,
        "COINBASE_EXCHANGE": ConnectionProvider.COINBASE,
        "MT5_BRIDGE": ConnectionProvider.MT5_BRIDGE,
    }
    if source not in providers:
        raise ValueError(f"historical candles are not supported for {source}")
    provider = providers[source]
    connection: ResolvedConnection | None
    binding_id = selection.data.get("connection_binding_id")
    if binding_id:
        binding = await store.get("provider_binding", UUID(binding_id), owner_id)
        if (
            binding is None
            or binding.data.get("account_id") != candidate.account_id
            or binding.data.get("lane") != selection.data.get("lane")
            or binding.data.get("verification_status") != "VERIFIED"
        ):
            raise ValueError("the selected market provider binding is unavailable")
        connection = await resolve_connection(db, owner_id, UUID(binding.data["connection_id"]))
        if connection.profile.provider != provider:
            raise ValueError("historical provider differs from selected market evidence")
    elif provider == ConnectionProvider.MT5_BRIDGE:
        raise ValueError("rerun market research to pin the broker's account binding")
    else:
        connection = await find_connection(db, owner_id, provider)
    if connection is None:
        raise ValueError(f"configure an active {provider.value} historical data connection first")
    account = await store.get("account", UUID(candidate.account_id), owner_id)
    if account is None or account.state == "DELETED":
        raise ValueError("the market research account is unavailable")
    timeframe = settings.strategy_research_timeframe
    if provider == ConnectionProvider.MT5_BRIDGE:
        native_timeframe = candidate.fingerprint.source_version.rsplit(":", 1)[-1]
        timeframe = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}.get(
            native_timeframe, timeframe
        )
    return {
        "market_selection_id": str(selection.id),
        "market_research_run_id": str(research_run.id),
        "account_id": candidate.account_id,
        "instrument": candidate.instrument,
        "category": candidate.category,
        "market_observed_at": candidate.fingerprint.observed_at.isoformat(),
        "historical_connection_id": str(connection.id),
        "historical_provider": provider.value,
        "historical_timeframe": timeframe,
    }


async def prepare_strategy_research(db: AsyncSession, market_run: ResourceRecord) -> list[UUID]:
    """Called with the parent row locked; stable IDs make delivery replayable."""
    store = ResourceStore(db)
    pending = []
    links = []
    for selection in await store.list("market_selection", market_run.owner_id):
        if selection.state != "ACTIVE_MARKET_ANALYSIS" or selection.data.get(
            "research_run_id"
        ) != str(market_run.id):
            continue
        run_id = uuid5(NAMESPACE_URL, f"strategy-research:{selection.id}")
        draft_id = uuid5(NAMESPACE_URL, f"strategy-draft:{selection.id}")
        existing = await store.get("strategy_research_run", run_id, market_run.owner_id)
        if existing is not None and existing.state == "RESEARCHING":
            started = datetime.fromisoformat(existing.data["started_at"])
            # Generation has a 10-minute hard task limit. Recover lost workers after 15.
            if datetime.now(UTC) - started > timedelta(minutes=15):
                await store.update(
                    existing, state="QUEUED", event_type="strategy_research.recovered"
                )
        instrument = selection.data.get("candidate", {}).get("listing", {}).get("symbol")
        link = {
            "market_selection_id": str(selection.id),
            "instrument": instrument,
            "draft_id": str(draft_id),
            "research_run_id": str(run_id),
        }
        if existing is None:
            try:
                basis = await resolve_strategy_basis(db, market_run.owner_id, selection.id)
            except (KeyError, LookupError, RuntimeError, ValueError) as exc:
                links.append({**link, "state": "BLOCKED", "reason": str(exc)})
                continue
            await store.create(
                "strategy_draft",
                market_run.owner_id,
                {
                    "origin": "AI_GENERATED",
                    "description": None,
                    "specification": None,
                    "proposed_specification": None,
                    "research_basis": basis,
                    "research_run_id": str(run_id),
                    "revision": 1,
                    "lifecycle_state": "QUEUED",
                    "provenance": {"origin": "AI_GENERATED", "trigger": "TOP_PAIR"},
                },
                state="QUEUED",
                record_id=draft_id,
                event_type="strategy_draft.automatically_queued",
            )
            existing = await store.create(
                "strategy_research_run",
                market_run.owner_id,
                {
                    "draft_id": str(draft_id),
                    "origin": "AI_GENERATED",
                    "description": None,
                    "trigger": "TOP_PAIR",
                    **basis,
                },
                state="QUEUED",
                record_id=run_id,
                event_type="strategy_research.queued",
            )
        links.append({**link, "state": existing.state})
        if existing.state == "QUEUED":
            pending.append(existing.id)
    if market_run.data.get("strategy_research") != links:
        await store.update(
            market_run,
            {**market_run.data, "strategy_research": links},
            event_type="research.strategy_pipeline_linked",
        )
    return pending
