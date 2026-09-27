"""Resolve historical authority from immutable, owner-scoped research identity."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.connections.resolution import ResolvedConnection, resolve_connection
from packages.shared.store import ResourceRecord, ResourceStore

ALLOWED_PROVIDERS = {
    "FOREX": {ConnectionProvider.TWELVE_DATA, ConnectionProvider.MT5_BRIDGE},
    "METALS": {ConnectionProvider.MT5_BRIDGE},
    "CRYPTOCURRENCY": {ConnectionProvider.COINBASE},
    "STOCKS": {ConnectionProvider.TWELVE_DATA, ConnectionProvider.MT5_BRIDGE},
}


async def resolve_backtest_basis(
    db: AsyncSession,
    owner_id: UUID,
    version: ResourceRecord,
) -> tuple[dict, ResolvedConnection]:
    store = ResourceStore(db)
    basis = version.data.get("research_basis")
    if not basis:
        draft = await store.get("strategy_draft", UUID(version.data["strategy_id"]), owner_id)
        basis = draft.data.get("research_basis") if draft else None
    if not basis or not basis.get("market_selection_id"):
        raise ValueError("strategy has no pinned market research selection; research it again")
    selection = await store.get("market_selection", UUID(basis["market_selection_id"]), owner_id)
    if selection is None:
        raise ValueError("strategy market selection is unavailable")
    account_id = str(selection.data["account_id"])
    if basis.get("account_id") != account_id:
        raise ValueError("strategy account differs from the market selection")
    account = await store.get("account", UUID(account_id), owner_id)
    if account is None or account.state == "DELETED":
        raise ValueError("strategy account is unavailable")
    binding_id = selection.data.get("connection_binding_id")
    if not binding_id:
        raise ValueError("market selection has no verified provider binding; rerun research")
    binding = await store.get("provider_binding", UUID(binding_id), owner_id)
    lane = selection.data["lane"]
    if (
        binding is None
        or binding.data.get("account_id") != account_id
        or binding.data.get("lane") != lane
        or binding.data.get("verification_status") != "VERIFIED"
    ):
        raise ValueError("strategy account/lane provider binding is no longer verified")
    connection = await resolve_connection(db, owner_id, UUID(binding.data["connection_id"]))
    if connection.profile.provider not in ALLOWED_PROVIDERS.get(lane["asset_class"], set()):
        raise ValueError(
            f"{connection.profile.provider.value} cannot backtest {lane['asset_class']}"
        )
    listing = selection.data["candidate"]["listing"]
    source = str(listing["provider"]).upper().replace("COINBASE_EXCHANGE", "COINBASE")
    if connection.profile.provider.value != source:
        raise ValueError("bound historical provider differs from the market evidence")
    timeframe = basis.get("historical_timeframe", "1h")
    if connection.profile.provider == ConnectionProvider.MT5_BRIDGE:
        cut = selection.data["candidate"]["fingerprint"].get("source_cut_id", "")
        timeframe = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}.get(
            cut.rsplit(":", 1)[-1], timeframe
        )
    return {
        **basis,
        "account_id": account_id,
        "instrument": listing["symbol"],
        "asset_class": lane["asset_class"],
        "connection_binding_id": str(binding.id),
        "historical_connection_id": str(connection.id),
        "historical_provider": connection.profile.provider.value,
        "historical_timeframe": timeframe,
        "research_history_timeframe": basis.get("historical_timeframe", timeframe),
        "tick_size": selection.data["candidate"].get("specification", {}).get("tick_size"),
    }, connection
