from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.journal.model import JournalEntry
from traderx.market_data.model import Instrument

ANALYTICS_DIMENSIONS = (
    "instrument",
    "asset_class",
    "source_type",
    "strategy_version",
    "time",
    "direction",
    "risk",
    "regime",
    "entry_quality",
    "behavior",
)


def aggregate(rows: list[dict[str, object]], dimension: str) -> dict[str, dict[str, Decimal | int]]:
    if dimension not in ANALYTICS_DIMENSIONS:
        raise ValueError("unsupported journal analytics dimension")
    result: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"count": 0, "net_pnl": Decimal("0"), "r": Decimal("0")}
    )
    for row in rows:
        bucket = str(row.get(dimension, "UNKNOWN"))
        result[bucket]["count"] = int(result[bucket]["count"]) + 1
        result[bucket]["net_pnl"] = Decimal(result[bucket]["net_pnl"]) + Decimal(
            str(row.get("net_pnl", "0"))
        )
        result[bucket]["r"] = Decimal(result[bucket]["r"]) + Decimal(
            str(row.get("r_multiple", "0"))
        )
    return dict(result)


def analytics_rows(database: Session) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry in database.scalars(select(JournalEntry)):
        instrument = database.get(Instrument, entry.instrument_id) if entry.instrument_id else None
        rows.append(
            {
                "instrument": instrument.symbol if instrument else "UNKNOWN",
                "asset_class": instrument.category if instrument else "UNKNOWN",
                "source_type": entry.source_type,
                "direction": entry.evidence.get("direction", "UNKNOWN"),
                "strategy_version": entry.evidence.get("strategy_version_id", "NONE"),
                "time": entry.closed_at.strftime("%Y-%m"),
                "risk": entry.evidence.get("risk_band", "UNRECORDED"),
                "regime": entry.evidence.get("regime", "UNRECORDED"),
                "entry_quality": entry.evidence.get("entry_quality", "UNRECORDED"),
                "behavior": entry.evidence.get("behavior", "UNRECORDED"),
                "net_pnl": str(entry.net_pnl),
                "r_multiple": str(entry.r_multiple or 0),
            }
        )
    return rows


def aggregate_all_dimensions(
    database: Session,
) -> dict[str, dict[str, dict[str, Decimal | int]]]:
    rows = analytics_rows(database)
    return {dimension: aggregate(rows, dimension) for dimension in ANALYTICS_DIMENSIONS}
