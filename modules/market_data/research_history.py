"""Explicit independent history bindings; broker quote/contract identity stays pinned."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from adapters.market_data.history import TIMEFRAMES, historical_candles
from adapters.market_data.public_research import public_history
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import ResolvedConnection, resolve_connection
from modules.market_data.research_store import ResearchDataStore
from modules.research.quantitative_features import FEATURE_VERSION, build_features, candle_frame
from packages.shared.config import settings
from packages.shared.store import ResourceStore

PRICE_SOURCES = {
    ConnectionProvider.DUKASCOPY,
    ConnectionProvider.CCXT,
    ConnectionProvider.YAHOO_FINANCE,
}


def verified_import_binding(bindings, account_id, connection_id, provider) -> bool:
    """Only verified candle bindings can authorize an independent history import."""
    purpose = "REFERENCE" if provider == ConnectionProvider.YAHOO_FINANCE else "HISTORY"
    return any(
        b.state != "DELETED"
        and b.data.get("account_id") == str(account_id)
        and b.data.get("connection_id") == str(connection_id)
        and b.data.get("verification_status") == "VERIFIED"
        and b.data.get("capability") == "CANDLES"
        and b.data.get("authority_purpose") == purpose
        for b in bindings
    )


def configuration_hash(connection: ResolvedConnection) -> str:
    return sha256(json.dumps(connection.profile.configuration, sort_keys=True).encode()).hexdigest()


async def cached_history(
    db,
    owner_id: UUID,
    account_id: UUID,
    connection: ResolvedConnection,
    instrument: str,
    start: datetime,
    end: datetime,
    timeframe: str,
):
    """Reuse accumulated owner/account/source-bound imports without changing frozen prices."""
    import pandas as pd

    from modules.backtesting.engine import BacktestCandle

    if connection.profile.provider not in PRICE_SOURCES:
        return None
    records = [
        r
        for r in await ResourceStore(db).list("market_dataset", owner_id)
        if r.data.get("account_id") == str(account_id)
        and r.data.get("connection_id") == str(connection.id)
        and r.data.get("instrument") == instrument
        and r.data.get("timeframe") == timeframe
        and r.data.get("source", {}).get("configuration_hash") == configuration_hash(connection)
    ]
    relevant = []
    for record in records:
        source = record.data["source"]
        left = datetime.fromisoformat(source["requested_start_at"])
        right = datetime.fromisoformat(source["requested_end_at"])
        if left < end and right > start:
            relevant.append((left, right, record))
    cursor = start
    for left, right, _ in sorted(relevant, key=lambda item: item[0]):
        if left > cursor:
            return None
        cursor = max(cursor, right)
    if cursor < end or not relevant:
        return None
    archive = ResearchDataStore(settings.research_data_root, owner_id)
    # First-seen overlapping observations win; new imports cannot revise existing evidence.
    relevant.sort(key=lambda item: item[2].created_at)
    frame = pd.concat([archive.read_frame(r.data["source"]["normalized"]) for _, _, r in relevant])
    frame = frame[~frame.index.duplicated(keep="first")].sort_index()
    seconds = TIMEFRAMES[timeframe][1]
    opens = frame.index - pd.Timedelta(seconds=seconds)
    frame = frame[(opens >= start) & (frame.index <= end)]
    if frame.empty:
        return None
    candles = [
        BacktestCandle(
            observed_at=at.to_pydatetime() - timedelta(seconds=seconds),
            **{key: str(row[key]) for key in ("open", "high", "low", "close", "volume")},
        )
        for at, row in frame.iterrows()
    ]
    refs = [str(r.id) for _, _, r in relevant]
    return candles, {
        "provider": connection.profile.provider.value,
        "source_version": "archive:" + sha256(":".join(refs).encode()).hexdigest(),
        "cached_dataset_ids": refs,
        "authority": "INDEPENDENT_RESEARCH",
        "execution_authority": False,
        "requested_start_at": start.isoformat(),
        "requested_end_at": end.isoformat(),
        "configuration_hash": configuration_hash(connection),
        "normalized": archive.frame(frame),
    }


async def independent_history_binding(
    db: AsyncSession, owner_id: UUID, account_id: UUID, lane: dict, instrument: str
):
    store = ResourceStore(db)
    bindings = sorted(
        [
            item
            for item in await store.list("provider_binding", owner_id)
            if item.data.get("account_id") == str(account_id)
            and item.data.get("lane") == lane
            and item.data.get("capability") == "CANDLES"
            and item.data.get("authority_purpose") == "HISTORY"
            and item.data.get("verification_status") == "VERIFIED"
        ],
        key=lambda item: (int(item.data.get("priority", 1)), str(item.id)),
    )
    if not bindings:
        return None
    binding = bindings[0]
    connection = await resolve_connection(db, owner_id, UUID(binding.data["connection_id"]))
    if connection.profile.provider not in PRICE_SOURCES:
        # Existing native history stays in the existing adapter / authority workflow.
        return None
    mapping = connection.profile.configuration.get("symbol_map", {}).get(instrument)
    if not isinstance(mapping, dict) or not mapping.get("symbol"):
        raise ValueError("verified HISTORY connection needs an explicit instrument symbol_map")
    if connection.profile.provider == ConnectionProvider.YAHOO_FINANCE:
        raise ValueError("Yahoo is an intermarket REFERENCE proxy, not the pair's primary HISTORY")
    if (
        connection.profile.provider == ConnectionProvider.CCXT
        and lane.get("asset_class") != "CRYPTOCURRENCY"
    ):
        raise ValueError("CCXT price history is only a cryptocurrency reference")
    return binding, connection


async def archived_history(
    connection: ResolvedConnection,
    owner_id: UUID,
    instrument: str,
    start: datetime,
    end: datetime,
    timeframe: str,
    *,
    account_id: UUID,
    native_loader=None,
):
    archive = ResearchDataStore(settings.research_data_root, owner_id)
    if connection.profile.provider in PRICE_SOURCES:
        candles, source = await public_history(
            connection, instrument, start, end, timeframe, archive
        )
    else:
        candles, source = await (native_loader or historical_candles)(
            connection, instrument, start, end, timeframe, account_id=account_id
        )
    seconds = TIMEFRAMES[timeframe][1]
    candles = [
        c
        for c in candles
        if start <= c.observed_at and c.observed_at.timestamp() + seconds <= end.timestamp()
    ]
    if not candles:
        raise ValueError("no completed history at the requested cutoff")
    normalized = archive.frame(candle_frame(candles, seconds))
    if connection.profile.provider == ConnectionProvider.DUKASCOPY and source.get("normalized"):
        source["bid_ask_normalized"] = source["normalized"]
    source = {
        **source,
        "normalized": normalized,
        "execution_authority": False,
        "owner_id": str(owner_id),
        "connection_id": str(connection.id),
        "requested_start_at": start.isoformat(),
        "requested_end_at": end.isoformat(),
        "configuration_hash": configuration_hash(connection)
        if hasattr(connection.profile, "configuration")
        else None,
    }
    return candles, source


async def persist_dataset(
    db: AsyncSession,
    owner_id: UUID,
    account_id: UUID,
    connection_id: UUID,
    instrument: str,
    timeframe: str,
    candles: list,
    source: dict,
) -> dict:
    store = ResourceStore(db)
    identity = (
        f"{owner_id}:{account_id}:{connection_id}:{instrument}:{timeframe}:"
        f"{source['normalized']['checksum']}"
    )
    record_id = uuid5(NAMESPACE_URL, f"research-dataset:{identity}")
    record = await store.get("market_dataset", record_id, owner_id)
    if record is None:
        record = await store.create(
            "market_dataset",
            owner_id,
            {
                "account_id": str(account_id),
                "connection_id": str(connection_id),
                "instrument": instrument,
                "timeframe": timeframe,
                "candle_count": len(candles),
                "start_at": candles[0].observed_at.isoformat(),
                "end_at": candles[-1].observed_at.isoformat(),
                "source": source,
                "execution_authority": False,
            },
            record_id=record_id,
            event_type="research_dataset.archived",
        )
    return {
        "dataset_id": str(record.id),
        "checksum": source["normalized"]["checksum"],
        "account_id": str(account_id),
        "instrument": instrument,
        "timeframe": timeframe,
    }


async def persist_features(
    db: AsyncSession,
    owner_id: UUID,
    dataset: dict,
    candles: list,
    timeframe: str,
    *,
    context: dict | None = None,
) -> dict:
    archive = ResearchDataStore(settings.research_data_root, owner_id)
    frame = build_features(candles, TIMEFRAMES[timeframe][1], intermarket=context)
    reference = archive.frame(frame, layer="features")
    store = ResourceStore(db)
    record_id = uuid5(
        NAMESPACE_URL,
        f"research-features:{owner_id}:{dataset['dataset_id']}:{reference['checksum']}",
    )
    record = await store.get("market_features", record_id, owner_id)
    if record is None:
        record = await store.create(
            "market_features",
            owner_id,
            {
                **dataset,
                "feature_version": FEATURE_VERSION,
                "archive": reference,
                "available_at": frame.index[-1].isoformat(),
                "feature_count": len(frame.columns),
                "row_count": len(frame),
                "execution_authority": False,
                "context_alignment": "BACKWARD_AVAILABILITY_ONLY",
            },
            record_id=record_id,
            event_type="research_features.archived",
        )
    latest = frame.iloc[-1].to_json()
    import json

    return {
        "feature_record_id": str(record.id),
        "feature_version": FEATURE_VERSION,
        "archive": reference,
        "latest": json.loads(latest),
        "available_at": frame.index[-1].isoformat(),
    }
