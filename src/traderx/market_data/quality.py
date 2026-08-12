from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from traderx.market_data.ingestion import CanonicalBar
from traderx.shared.types import DataQuality


@dataclass(frozen=True, slots=True)
class QualityResult:
    quality: DataQuality
    reason_codes: tuple[str, ...]


def assess_bars(bars: list[CanonicalBar], *, now: datetime, max_age: timedelta) -> QualityResult:
    reasons: list[str] = []
    if not bars:
        return QualityResult(DataQuality.UNKNOWN, ("NO_MARKET_DATA",))
    for bar in bars:
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            reasons.append("INVALID_OHLC")
        if bar.spread is not None and bar.spread < Decimal("0"):
            reasons.append("NEGATIVE_SPREAD")
    if now - bars[-1].observed_at > max_age:
        reasons.append("STALE_DATA")
    if len({bar.observed_at for bar in bars}) != len(bars):
        reasons.append("CONTRADICTORY_REVISION")
    return QualityResult(
        DataQuality.QUARANTINED if reasons else DataQuality.VERIFIED, tuple(sorted(set(reasons)))
    )
