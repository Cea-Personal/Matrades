from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from traderx.market_data.ingestion import CanonicalBar
from traderx.shared.types import DataQuality


@dataclass(frozen=True, slots=True)
class QualityResult:
    quality: DataQuality
    reason_codes: tuple[str, ...]
    gap_count: int = 0
    latest_observation_at: datetime | None = None


class DataPurpose(StrEnum):
    MARKET_SELECTION = "MARKET_SELECTION"
    OPPORTUNITY_MONITORING = "OPPORTUNITY_MONITORING"
    BACKTEST = "BACKTEST"


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    purpose: DataPurpose
    max_age: timedelta
    expected_interval: timedelta
    maximum_gaps: int = 0
    maximum_spread: Decimal | None = None
    price_tick: Decimal | None = None
    volume_step: Decimal | None = None


def find_time_gaps(
    bars: list[CanonicalBar], *, expected_interval: timedelta
) -> tuple[tuple[datetime, datetime], ...]:
    """Return missing half-open intervals without manufacturing observations."""

    if expected_interval <= timedelta(0):
        raise ValueError("expected interval must be positive")
    ordered = sorted({bar.observed_at for bar in bars})
    gaps: list[tuple[datetime, datetime]] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        cursor = previous + expected_interval
        if cursor < current:
            gaps.append((cursor, current))
    return tuple(gaps)


def assess_bars(
    bars: list[CanonicalBar],
    *,
    now: datetime,
    max_age: timedelta | None = None,
    policy: QualityPolicy | None = None,
) -> QualityResult:
    """Apply the purpose-specific quality policy and fail closed on uncertain data."""

    if policy is None:
        if max_age is None:
            raise ValueError("max_age or a purpose-aware policy is required")
        policy = QualityPolicy(
            purpose=DataPurpose.MARKET_SELECTION,
            max_age=max_age,
            expected_interval=max_age,
            maximum_gaps=2**31 - 1,
        )
    reasons: list[str] = []
    if not bars:
        return QualityResult(DataQuality.UNKNOWN, ("NO_MARKET_DATA",))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("quality assessment now must be timezone-aware")
    ordered = sorted(bars, key=lambda item: (item.observed_at, item.revision))
    for bar in bars:
        if bar.observed_at.tzinfo is None or bar.observed_at.utcoffset() is None:
            reasons.append("NAIVE_TIMESTAMP")
        elif bar.observed_at > now:
            reasons.append("FUTURE_TIMESTAMP")
        if (
            bar.low > min(bar.open, bar.close)
            or bar.high < max(bar.open, bar.close)
            or bar.high < bar.low
            or min(bar.open, bar.high, bar.low, bar.close) <= 0
        ):
            reasons.append("INVALID_OHLC")
        if bar.spread is not None and bar.spread < Decimal("0"):
            reasons.append("NEGATIVE_SPREAD")
        if (
            policy.maximum_spread is not None
            and bar.spread is not None
            and bar.spread > policy.maximum_spread
        ):
            reasons.append("EXCESSIVE_SPREAD")
        if policy.price_tick is not None and any(
            value % policy.price_tick != 0 for value in (bar.open, bar.high, bar.low, bar.close)
        ):
            reasons.append("PRICE_TICK_MISALIGNMENT")
        if (
            policy.volume_step is not None
            and bar.volume is not None
            and bar.volume % policy.volume_step != 0
        ):
            reasons.append("VOLUME_STEP_MISALIGNMENT")
    latest = max(bar.observed_at for bar in bars)
    if latest.tzinfo is not None and latest.utcoffset() is not None and now - latest > policy.max_age:
        reasons.append("STALE_DATA")
    revisions: dict[tuple[datetime, int], CanonicalBar] = {}
    for bar in ordered:
        key = (bar.observed_at, bar.revision)
        if key in revisions and revisions[key] != bar:
            reasons.append("CONTRADICTORY_REVISION")
        revisions[key] = bar
    gaps = find_time_gaps(bars, expected_interval=policy.expected_interval)
    if len(gaps) > policy.maximum_gaps:
        reasons.append("EXCESSIVE_GAPS")
    quality = DataQuality.VERIFIED
    if "STALE_DATA" in reasons and len(set(reasons)) == 1:
        quality = DataQuality.STALE
    elif "CONTRADICTORY_REVISION" in reasons:
        quality = DataQuality.CONTRADICTORY
    elif reasons:
        quality = DataQuality.QUARANTINED
    return QualityResult(
        quality,
        tuple(sorted(set(reasons))),
        gap_count=len(gaps),
        latest_observation_at=latest,
    )


def project_fail_closed_status(current_status: str, result: QualityResult) -> str:
    """Quality can quarantine an instrument, but it never activates one."""

    if result.quality != DataQuality.VERIFIED:
        return "QUARANTINED"
    return "INACTIVE" if current_status == "QUARANTINED" else current_status
