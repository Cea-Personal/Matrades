from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from modules.performance.models import PerformanceRecord


def aggregate(
    records: list[PerformanceRecord], dimension: str
) -> dict[str, dict[str, Decimal | int]]:
    grouped = defaultdict(list)
    for item in records:
        grouped[str(getattr(item, dimension))].append(item)
    return {
        key: {
            "trades": len(items),
            "pnl": sum((x.pnl for x in items), Decimal("0")),
            "expectancy": sum((x.pnl for x in items), Decimal("0")) / len(items),
            "r": sum((x.pnl / x.risk for x in items if x.risk > 0), Decimal("0")) / len(items),
        }
        for key, items in grouped.items()
    }


def wrapper_metrics(records: list[PerformanceRecord]) -> dict[str, dict[str, Decimal | int]]:
    """Compare spot, CFD, and futures results without mixing cost semantics."""
    return aggregate(records, "instrument_type") if records else {}
