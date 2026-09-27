"""Versioned, deterministic profiles using only the supplied completed candles.

OHLCV is not order-book evidence. Session/volume measures are descriptive
proxies; absent execution and calendar observations remain explicitly unknown.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from modules.backtesting.engine import BacktestCandle

PROFILE_VERSION = "pair-profile-v1"


def regime_features(candles: list[BacktestCandle]) -> dict[str, Decimal]:
    window = candles[-21:]
    moves = [b.close - a.close for a, b in zip(window, window[1:], strict=False)]
    distance = sum((abs(x) for x in moves), Decimal(0))
    efficiency = abs(sum(moves, Decimal(0))) / distance if distance else Decimal(0)
    ranges = [c.high - c.low for c in candles[-40:]]
    recent = sum(ranges[-10:], Decimal(0)) / max(1, len(ranges[-10:]))
    baseline = ranges[:-10]
    reference = sum(baseline, Decimal(0)) / len(baseline) if baseline else recent
    return {
        "regime_ready": Decimal(len(candles) >= 21),
        "trend_efficiency": efficiency,
        "trend_direction": Decimal(1 if sum(moves) > 0 else -1 if sum(moves) < 0 else 0),
        "relative_volatility": recent / reference if reference else Decimal(0),
    }


def regime_from_features(features: dict[str, Decimal]) -> dict[str, str]:
    news = (
        {
            "news": {-2: "UNKNOWN", -1: "PRE_NEWS", 0: "NORMAL", 1: "POST_NEWS"}.get(
                int(features["news_regime"]), "UNKNOWN"
            )
        }
        if "news_regime" in features
        else {}
    )
    if not features.get("regime_ready"):
        return {"behaviour": "UNKNOWN", "direction": "UNKNOWN", "volatility": "UNKNOWN", **news}
    ratio = features["relative_volatility"]
    result = {
        **news,
        "behaviour": "TRENDING" if features["trend_efficiency"] >= Decimal("0.35") else "RANGING",
        "direction": {1: "BULLISH", -1: "BEARISH", 0: "FLAT"}[int(features["trend_direction"])],
        "volatility": "HIGH_VOLATILITY"
        if ratio >= Decimal("1.5")
        else "LOW_VOLATILITY"
        if ratio <= Decimal("0.75")
        else "NORMAL_VOLATILITY",
    }
    return result


def regime_key(regime: dict[str, str]) -> str:
    return ":".join(regime[key] for key in ("behaviour", "direction", "volatility"))


def regime_matches(wanted: list[str], features: dict[str, Decimal]) -> bool:
    """Alternatives are OR; dimensions within a colon-separated entry are AND."""
    if not wanted:
        return True
    regime = regime_from_features(features)
    if regime["behaviour"] == "UNKNOWN":
        return False
    tags = set(regime.values())
    aliases = {
        "TREND": "TRENDING",
        "RANGE": "RANGING",
        "VOLATILE": "HIGH_VOLATILITY",
        "NORMAL_NEWS": "NORMAL",
    }
    return any(
        all(
            tag.strip().upper() != "UNKNOWN"
            and aliases.get(tag.strip().upper(), tag.strip().upper()) in tags
            for tag in item.split(":")
        )
        for item in wanted
    )


def news_state(instrument: str, at: datetime, calendar: list[dict] | None) -> str:
    if calendar is None:
        return "UNKNOWN"
    symbol = instrument.upper().replace("/", "").replace("-", "")
    offsets = []
    for event in calendar:
        if str(event.get("impact", "")).upper() != "HIGH" or event.get("currency") not in {
            symbol[:3],
            symbol[3:6],
        }:
            continue
        scheduled = datetime.fromisoformat(event["scheduled_at"])
        if scheduled.tzinfo is None:
            continue
        offset = (scheduled - at).total_seconds()
        if abs(offset) <= 1800:
            offsets.append(offset)
    if not offsets:
        return "NORMAL"
    return "PRE_NEWS" if min(offsets, key=abs) >= 0 else "POST_NEWS"


def news_features(
    instrument: str, at: datetime, calendar: list[dict] | None, *, observed_state: str | None = None
) -> dict[str, Decimal]:
    state = observed_state if observed_state is not None else news_state(instrument, at, calendar)
    return {
        "news_regime": Decimal(
            {"UNKNOWN": -2, "PRE_NEWS": -1, "NORMAL": 0, "POST_NEWS": 1}.get(state, -2)
        )
    }


def profile_pair(
    candles: list[BacktestCandle],
    instrument: str,
    *,
    as_of: datetime | None = None,
    calendar: list[dict] | None = None,
    spread: Decimal | None = None,
    slippage: Decimal | None = None,
) -> dict:
    if not candles:
        raise ValueError("Pair profiling requires completed candle evidence")
    # The caller supplies a closed-candle cut; never inspect future observations.
    candles = [c for c in candles if as_of is None or c.observed_at <= as_of]
    if not candles:
        raise ValueError("No candles exist before the profile cut")
    features = regime_features(candles)
    regime = regime_from_features(features)
    at = as_of or candles[-1].observed_at
    regime["news"] = news_state(instrument, at, calendar)
    returns = [float(b.close / a.close - 1) for a, b in zip(candles, candles[1:], strict=False)]
    reversals = sum(a * b < 0 for a, b in zip(returns, returns[1:], strict=False))
    autocorrelation = None
    if len(returns) >= 3:
        left, right = returns[:-1], returns[1:]
        lmean, rmean = mean(left), mean(right)
        numerator = sum((a - lmean) * (b - rmean) for a, b in zip(left, right, strict=True))
        denominator = (
            sum((a - lmean) ** 2 for a in left) * sum((b - rmean) ** 2 for b in right)
        ) ** 0.5
        if denominator:
            autocorrelation = numerator / denominator
    news_sensitivity = {
        "status": "UNAVAILABLE",
        "calendar_available": calendar is not None,
        "event_count": 0,
    }
    if calendar is not None and len(candles) >= 2:
        period = (candles[1].observed_at - candles[0].observed_at).total_seconds()
        normalized = instrument.upper().replace("/", "").replace("-", "")
        ratios = []
        for event in calendar:
            if (
                event.get("currency") not in {normalized[:3], normalized[3:6]}
                or str(event.get("impact", "")).upper() != "HIGH"
            ):
                continue
            scheduled = datetime.fromisoformat(event["scheduled_at"])
            if scheduled.tzinfo is None:
                continue
            # Use complete bars strictly after the event and a preceding range baseline.
            before = [
                c.high - c.low
                for c in candles
                if period <= (scheduled - c.observed_at).total_seconds() <= period * 10
            ]
            after = [
                c.high - c.low
                for c in candles
                if 0 <= (c.observed_at - scheduled).total_seconds() < period * 2
            ]
            if len(before) >= 5 and after and sum(before):
                ratios.append(
                    float(
                        (sum(after, Decimal(0)) / len(after))
                        / (sum(before, Decimal(0)) / len(before))
                    )
                )
        news_sensitivity.update(
            {
                "status": "DESCRIPTIVE_RANGE_PROXY" if ratios else "INSUFFICIENT_EVENT_SAMPLES",
                "event_count": len(ratios),
                "mean_post_event_range_ratio": mean(ratios) if ratios else None,
                "candle_resolution_seconds": period,
            }
        )
    sessions = {}
    for name, zone, start, end in (
        ("LONDON", "Europe/London", 8, 17),
        ("NEW_YORK", "America/New_York", 8, 17),
        ("TOKYO", "Asia/Tokyo", 9, 18),
    ):
        sample = [
            c for c in candles if start <= c.observed_at.astimezone(ZoneInfo(zone)).hour < end
        ]
        sessions[name] = {
            "candle_count": len(sample),
            "mean_range": str(sum((c.high - c.low for c in sample), Decimal(0)) / len(sample))
            if sample
            else None,
            "mean_volume_proxy": str(sum((c.volume for c in sample), Decimal(0)) / len(sample))
            if sample
            else None,
        }
    return {
        "version": PROFILE_VERSION,
        "instrument": instrument,
        "as_of": at.isoformat(),
        "candle_count": len(candles),
        "start_at": candles[0].observed_at.isoformat(),
        "end_at": candles[-1].observed_at.isoformat(),
        "regime": regime,
        "regime_key": regime_key(regime),
        "volatility": {
            "return_std_per_bar": pstdev(returns) if returns else None,
            "mean_return_per_bar": mean(returns) if returns else None,
            "relative_range": str(features["relative_volatility"]),
        },
        "trend_efficiency": str(features["trend_efficiency"]),
        "mean_reversion": {
            "lag_one_return_autocorrelation": autocorrelation,
            "direction_reversal_rate_proxy": reversals / (len(returns) - 1)
            if len(returns) > 1
            else None,
        },
        "session_behaviour": sessions,
        "liquidity": {
            "status": "PROXY_ONLY",
            "spread_assumption": str(spread) if spread is not None else None,
            "cost_basis": "CONFIGURED_SIMULATION_ASSUMPTIONS_NOT_EXECUTION_MEASUREMENTS",
            "slippage_assumption": str(slippage) if slippage is not None else None,
        },
        "news_sensitivity": news_sensitivity,
        "limitations": [
            "Volume and bar ranges are not order-book liquidity or measured slippage",
            "News sensitivity requires event-aligned historical observations",
            "Regime thresholds are fixed research heuristics, not learned optimal parameters",
        ],
    }
