from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.shared.types import MarketCategory


@dataclass(frozen=True, slots=True)
class LiquidityMetrics:
    turnover: Decimal
    spread_bps: Decimal
    depth: Decimal
    estimated_slippage_bps: Decimal
    execution_quality: Decimal = Decimal("0")
    method_version: str = "asset-liquidity-v1"
    evidence: tuple[str, ...] = ()


def assess_liquidity(*, turnover: Decimal, spread_bps: Decimal, depth: Decimal) -> LiquidityMetrics:
    if min(turnover, depth) < 0 or spread_bps < 0:
        raise ValueError("liquidity metrics cannot be negative")
    # Penalize thin books and spreads; the formula is deliberately simple and versionable.
    slippage = spread_bps / Decimal("2") + (Decimal("100000") / max(depth, Decimal("1")))
    execution_quality = _bounded(Decimal("1") - min(slippage, Decimal("100")) / Decimal("100"))
    return LiquidityMetrics(
        turnover,
        spread_bps,
        depth,
        slippage,
        execution_quality,
        evidence=("TURNOVER", "SPREAD", "DEPTH"),
    )


def assess_asset_liquidity(
    *,
    category: MarketCategory,
    turnover: Decimal,
    spread_bps: Decimal,
    quoted_depth: Decimal | None = None,
    tick_volume: Decimal | None = None,
    open_interest: Decimal | None = None,
    observed_slippage_bps: Decimal | None = None,
) -> LiquidityMetrics:
    """Use only class-appropriate evidence and identify every proxy in the result."""

    values = (turnover, spread_bps) + tuple(
        value
        for value in (quoted_depth, tick_volume, open_interest, observed_slippage_bps)
        if value is not None
    )
    if any(value < 0 for value in values):
        raise ValueError("liquidity metrics cannot be negative")

    evidence: list[str] = ["TURNOVER", "SPREAD"]
    if category == MarketCategory.CRYPTO:
        if quoted_depth is None:
            raise ValueError("cryptocurrency liquidity requires quoted depth")
        depth = quoted_depth
        evidence.append("QUOTED_DEPTH")
    elif category == MarketCategory.COMMODITY:
        if open_interest is None and tick_volume is None:
            raise ValueError("commodity liquidity requires open interest or tick volume")
        depth = open_interest if open_interest is not None else tick_volume or Decimal("0")
        evidence.append("OPEN_INTEREST" if open_interest is not None else "TICK_VOLUME_PROXY")
    else:
        if tick_volume is None:
            raise ValueError("forex liquidity requires broker tick volume")
        depth = tick_volume
        evidence.append("TICK_VOLUME_PROXY")

    modeled = spread_bps / Decimal("2") + Decimal("100000") / max(depth, Decimal("1"))
    slippage = observed_slippage_bps if observed_slippage_bps is not None else modeled
    evidence.append("OBSERVED_SLIPPAGE" if observed_slippage_bps is not None else "MODELED_SLIPPAGE")
    execution_quality = _bounded(
        Decimal("1")
        - min(spread_bps, Decimal("50")) / Decimal("100")
        - min(slippage, Decimal("50")) / Decimal("100")
    )
    return LiquidityMetrics(
        turnover=turnover,
        spread_bps=spread_bps,
        depth=depth,
        estimated_slippage_bps=slippage,
        execution_quality=execution_quality,
        evidence=tuple(evidence),
    )


def _bounded(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value))
