"""Read-only chart context and overlay projection.

Chart data is presentation evidence only.  No chart method accepts an execution
action or returns an authorization/command object.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from packages.shared.store import ResourceStore


class ChartCandle(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")


class ChartOverlay(BaseModel):
    kind: str
    label: str
    price: Decimal | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChartContext(BaseModel):
    trade_id: UUID
    instrument: str
    timeframe: str
    source_time: datetime
    freshness: str
    candles: list[ChartCandle] = Field(default_factory=list)
    overlays: list[ChartOverlay] = Field(default_factory=list)
    read_only: bool = True
    mapping_status: str = "UNAVAILABLE"
    source: str | None = None


async def authoritative_chart(
    store: ResourceStore,
    *,
    owner_id: UUID,
    trade_id: UUID,
    instrument: str,
    timeframe: str,
    trade_plan_id: UUID | None = None,
) -> ChartContext:
    """Project only persisted market/broker facts; charts never issue commands."""
    candles: list[ChartCandle] = []
    source: str | None = None
    for record in await store.list("chart_candle", owner_id):
        data = record.data
        if data.get("instrument") != instrument or data.get("timeframe", "1h") != timeframe:
            continue
        candles.append(ChartCandle.model_validate(data))
        source = str(data.get("source", source or "authoritative_market_data"))
    if not candles:
        for record in await store.list("market_observation", owner_id):
            data = record.data
            if data.get("instrument") != instrument:
                continue
            price = data.get("price") or data.get("bid") or data.get("ask")
            observed = data.get("observed_at")
            if price is None or observed is None:
                continue
            candles.append(
                ChartCandle(
                    timestamp=observed,
                    open=Decimal(str(price)),
                    high=Decimal(str(data.get("ask", price))),
                    low=Decimal(str(data.get("bid", price))),
                    close=Decimal(str(price)),
                    volume=Decimal(str(data.get("volume", 0))),
                )
            )
            source = str(data.get("source", "market_observation"))
    candles.sort(key=lambda item: item.timestamp)
    overlays: list[ChartOverlay] = []
    if trade_plan_id is not None:
        plan = await store.get("trade_plan", trade_plan_id, owner_id)
        if plan is not None:
            construction = plan.data.get("construction", {})
            for key, label in (("entry", "Entry"), ("stop_loss", "Stop Loss")):
                if construction.get(key) is not None:
                    overlays.append(
                        ChartOverlay(kind=key, label=label, price=construction[key])
                    )
            for index, target in enumerate(construction.get("targets", []), start=1):
                overlays.append(
                    ChartOverlay(kind="take_profit", label=f"Take Profit {index}", price=target)
                )
    for record in await store.list("journal_entry", owner_id):
        if record.data.get("trade_id") == str(trade_id):
            overlays.append(
                ChartOverlay(
                    kind="journal",
                    label=str(record.data.get("text", "Journal observation"))[:160],
                    timestamp=record.updated_at,
                )
            )
    freshness = "FRESH" if candles else "UNAVAILABLE"
    return ChartContext(
        trade_id=trade_id,
        instrument=instrument,
        timeframe=timeframe,
        source_time=candles[-1].timestamp if candles else datetime.now(UTC),
        freshness=freshness,
        candles=candles[-500:],
        overlays=overlays,
        mapping_status="MAPPED" if candles else "UNMAPPED",
        source=source,
    )


def empty_chart(trade_id: UUID, instrument: str, timeframe: str = "1h") -> ChartContext:
    return ChartContext(
        trade_id=trade_id,
        instrument=instrument,
        timeframe=timeframe,
        source_time=datetime.now(UTC),
        freshness="UNAVAILABLE",
    )
