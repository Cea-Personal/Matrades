from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


def aggregate(rows: list[dict[str, object]], dimension: str) -> dict[str, dict[str, Decimal | int]]:
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
