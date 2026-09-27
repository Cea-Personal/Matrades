"""Deterministic feature and fingerprint computation for research ranking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from statistics import fmean, pstdev

from modules.research.models import (
    MarketFingerprint,
    ResearchSnapshot,
    TypedMarketFingerprint,
    TypedResearchSnapshot,
)
from modules.research.sessions import weekend_close


class IneligibleResearchEvidence(ValueError):
    """A candidate failed a deterministic research eligibility gate."""


def typed_fingerprint(
    snapshot: TypedResearchSnapshot,
    *,
    now: datetime | None = None,
) -> tuple[TypedMarketFingerprint, float, list[str]]:
    """Rank opportunity quality, not raw volume or expected profitability.

    Weights are research heuristics, not calibrated win probabilities. Unknown
    optional inputs stay neutral and are explicitly recorded. Higher-timeframe
    agreement uses coarser samples of the same history, not an independent feed.
    """
    now = now or datetime.now(UTC)
    prices = snapshot.closes
    if len(prices) < 20:
        raise IneligibleResearchEvidence("INSUFFICIENT_HISTORY: at least 20 candles required")
    if not all(isfinite(value) and value > 0 for value in prices):
        raise IneligibleResearchEvidence("INVALID_PRICE_HISTORY")
    if not all(isfinite(value) for value in (snapshot.bid, snapshot.ask, snapshot.volume)):
        raise IneligibleResearchEvidence("NON_FINITE_QUOTE")
    if snapshot.ask < snapshot.bid:
        raise IneligibleResearchEvidence("CROSSED_QUOTE")
    close = weekend_close(snapshot.listing.asset_class, now)
    quote_time = snapshot.quote_observed_at or snapshot.observed_at
    age = (now - quote_time).total_seconds()
    if age < -300:
        raise IneligibleResearchEvidence("FUTURE_QUOTE_TIMESTAMP")
    if age > 900 and (close is None or quote_time < close - timedelta(hours=3)):
        raise IneligibleResearchEvidence("STALE_QUOTE")
    if snapshot.candle_observed_at:
        candle_age = (now - snapshot.candle_observed_at).total_seconds()
        if candle_age < -300:
            raise IneligibleResearchEvidence("FUTURE_CANDLE_TIMESTAMP")
        reference = close or now
        if (reference - snapshot.candle_observed_at).total_seconds() > max(
            snapshot.timeframe_seconds * 3, 10800 if close else 0
        ):
            raise IneligibleResearchEvidence("STALE_CANDLES")
    moves = [b - a for a, b in zip(prices, prices[1:], strict=False)]
    movement = fmean(abs(value) for value in moves)
    if movement <= 0:
        raise IneligibleResearchEvidence("NO_PRICE_MOVEMENT")
    spread_ratio = (snapshot.ask - snapshot.bid) / movement
    if snapshot.spread_verified and spread_ratio > 0.5:
        raise IneligibleResearchEvidence("EXCESSIVE_SPREAD_TO_MOVEMENT")
    limitations = []
    if close:
        limitations.append("MARKET_CLOSED: last-session evidence is research-only; no entry signal")
    if snapshot.quote_observed_at is None:
        limitations.append("Provider quote timestamp unavailable; receipt freshness only")
    if snapshot.candle_observed_at is None:
        limitations.append("Provider candle timestamp unavailable")
    if not snapshot.spread_verified:
        limitations.append("Actual bid/ask spread unavailable; neutral cost score")
    limitations.append("Broker execution and session availability require later validation")
    returns = [b / a - 1 for a, b in zip(prices, prices[1:], strict=False)]
    recent = moves[-20:]
    if sum(abs(value) for value in recent) == 0:
        raise IneligibleResearchEvidence("NO_RECENT_PRICE_MOVEMENT")
    efficiency = abs(sum(recent)) / sum(abs(value) for value in recent)
    recent_move = fmean(abs(value) for value in returns[-20:])
    baseline_move = fmean(abs(value) for value in returns)
    relative_volatility = recent_move / baseline_move
    volatility_suitability = _clamp(1 - abs(relative_volatility - 1) / 2)
    short_direction = prices[-1] - fmean(prices[-5:])
    coarse = prices[::-4][::-1]
    long_direction = coarse[-1] - fmean(coarse[-5:])
    alignment = 1.0 if short_direction * long_direction > 0 else 0.0
    if short_direction == 0 or long_direction == 0:
        alignment = 0.5
    limitations.append("Timeframe agreement uses 4-bar sampled closes, not independent candles")
    limitations.append("Raw volume is not comparable across providers; liquidity not inferred")
    low, high = min(prices[-20:]), max(prices[-20:])
    range_position = (prices[-1] - low) / (high - low) if high > low else 0.5
    structure = range_position if sum(recent) > 0 else 1 - range_position
    event = 1 - snapshot.event_risk if snapshot.event_risk is not None else 0.5
    if snapshot.event_risk is None:
        limitations.append("Economic-event risk unavailable; neutral event score")
    cost = _clamp(1 - spread_ratio / 0.5) if snapshot.spread_verified else 0.5
    criteria = {
        "trend_strength": efficiency,
        "market_structure": structure,
        "volatility_suitability": volatility_suitability,
        "trading_cost": cost,
        "timeframe_alignment": alignment,
        "event_suitability": event,
        "spread_to_movement": spread_ratio if snapshot.spread_verified else None,
        "relative_volatility": relative_volatility,
        "direction": 1.0 if sum(recent) > 0 else -1.0 if sum(recent) < 0 else 0.0,
    }
    score = 100 * (
        efficiency * 0.20
        + structure * 0.15
        + volatility_suitability * 0.20
        + cost * 0.20
        + alignment * 0.15
        + event * 0.10
    )
    quality = 0.5 + 0.2 * snapshot.spread_verified
    quality += 0.15 * (snapshot.quote_observed_at is not None)
    quality += 0.15 * (snapshot.candle_observed_at is not None)
    regime = (
        "HIGH_VOLATILITY"
        if relative_volatility > 2
        else "TRENDING"
        if efficiency >= 0.35
        else "RANGING"
    )
    result = TypedMarketFingerprint(
        listing_id=snapshot.listing.id,
        asset_class=snapshot.listing.asset_class,
        instrument_type=snapshot.listing.instrument_type,
        observed_at=snapshot.observed_at,
        source_cut_id=snapshot.source_cut_id,
        regime=regime,
        trend_score=round(efficiency, 6),
        volatility_score=round(volatility_suitability, 6),
        liquidity_score=0.5,
        data_quality=round(quality, 6),
        criteria={
            key: round(value, 6) if value is not None else None for key, value in criteria.items()
        },
        limitations=limitations,
        market_session="WEEKEND_CLOSED" if close else "NO_WEEKEND_CLOSURE",
        quote_observed_at=snapshot.quote_observed_at,
        candle_observed_at=snapshot.candle_observed_at,
        session_close_reference=close,
    )
    evidence = [f"Deterministic research score={score:.4f}; regime={regime}"]
    evidence += [f"{key}={value}" for key, value in result.criteria.items()]
    evidence += limitations
    return result, round(score, 6), evidence


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def fingerprint(snapshot: ResearchSnapshot) -> tuple[MarketFingerprint, float, list[str]]:
    closes = snapshot.closes
    returns = [
        (current - previous) / previous
        for previous, current in zip(closes, closes[1:], strict=False)
        if previous
    ]
    trend = _clamp(0.5 + ((closes[-1] / closes[0]) - 1.0) * 8.0)
    volatility = _clamp(pstdev(returns) * 40.0 if len(returns) > 1 else 0.0)
    mid = (snapshot.bid + snapshot.ask) / 2.0
    spread = _clamp(((snapshot.ask - snapshot.bid) / mid) * 500.0) if mid else 1.0
    liquidity = _clamp(snapshot.volume / 1_000_000.0)
    directional_strength = abs(trend - 0.5) * 2.0
    regime = (
        "HIGH_VOLATILITY"
        if volatility >= 0.65
        else "TRENDING"
        if directional_strength >= 0.35
        else "RANGING"
    )

    optional = [
        snapshot.macro_score,
        snapshot.sentiment_score,
        snapshot.event_risk,
        snapshot.positioning_score,
        snapshot.correlation_risk,
    ]
    quality = 0.5 + (sum(value is not None for value in optional) * 0.1)
    fundamental = snapshot.macro_score
    sentiment = snapshot.sentiment_score
    event_penalty = snapshot.event_risk or 0.0
    correlation_penalty = snapshot.correlation_risk or 0.0

    components = [
        directional_strength * 0.28,
        (1.0 - volatility) * 0.16,
        liquidity * 0.12,
        (1.0 - spread) * 0.12,
        ((fundamental + 1.0) / 2.0 if fundamental is not None else 0.5) * 0.12,
        ((sentiment + 1.0) / 2.0 if sentiment is not None else 0.5) * 0.10,
        (1.0 - event_penalty) * 0.05,
        (1.0 - correlation_penalty) * 0.05,
    ]
    deterministic_score = _clamp(fmean(components) * len(components)) * 100.0
    evidence = [
        f"{snapshot.source} snapshot at {snapshot.observed_at.isoformat()}",
        (
            f"{regime.lower().replace('_', ' ')} regime; "
            f"trend {trend:.3f}; volatility {volatility:.3f}"
        ),
        f"liquidity {liquidity:.3f}; spread penalty {spread:.3f}; data quality {quality:.2f}",
    ]
    if fundamental is None:
        evidence.append("Fundamental data unavailable; neutral contribution used")
    if sentiment is None:
        evidence.append("Sentiment data unavailable; neutral contribution used")

    result = MarketFingerprint(
        instrument=snapshot.instrument,
        category=snapshot.category,
        observed_at=snapshot.observed_at,
        source=snapshot.source,
        source_version=snapshot.source_version,
        regime=regime,
        trend_score=round(trend, 6),
        volatility_score=round(volatility, 6),
        liquidity_score=round(liquidity, 6),
        spread_score=round(spread, 6),
        fundamental_score=fundamental,
        sentiment_score=sentiment,
        event_risk=snapshot.event_risk,
        positioning_score=snapshot.positioning_score,
        correlation_risk=snapshot.correlation_risk,
        data_quality=round(quality, 2),
    )
    return result, round(deterministic_score, 6), evidence
