"""Deterministic feature and fingerprint computation for research ranking."""

from __future__ import annotations

from statistics import fmean, pstdev

from modules.research.models import MarketFingerprint, ResearchSnapshot


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
