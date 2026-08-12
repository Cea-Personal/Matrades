from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LiquidityMetrics:
    turnover: Decimal
    spread_bps: Decimal
    depth: Decimal
    estimated_slippage_bps: Decimal


def assess_liquidity(*, turnover: Decimal, spread_bps: Decimal, depth: Decimal) -> LiquidityMetrics:
    if min(turnover, depth) < 0 or spread_bps < 0:
        raise ValueError("liquidity metrics cannot be negative")
    # Penalize thin books and spreads; the formula is deliberately simple and versionable.
    slippage = spread_bps / Decimal("2") + (Decimal("100000") / max(depth, Decimal("1")))
    return LiquidityMetrics(turnover, spread_bps, depth, slippage)
