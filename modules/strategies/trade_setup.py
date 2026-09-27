"""Evidence-timestamped indicative trade levels for a researched strategy."""

from datetime import datetime, timedelta
from decimal import Decimal

from modules.backtesting.engine import BacktestCandle
from modules.research.sessions import weekend_close
from modules.strategies.pair_profile import (
    news_features,
    regime_from_features,
    regime_key,
    regime_matches,
)
from modules.strategies.signals import entry_matches, protection_levels, strategy_features
from packages.strategy_sdk.schema import StrategySpecification


def build_strategy_setup(
    strategy: StrategySpecification,
    candles: list[BacktestCandle],
    *,
    now: datetime,
    timeframe_seconds: int,
    tick_size: Decimal | None = None,
    calendar: list[dict] | None = None,
) -> dict:
    result = {
        "status": "WAIT",
        "instrument": strategy.instruments[0],
        "entry": None,
        "stop_loss": None,
        "take_profits": [],
        "risk_per_trade_percent": str(strategy.risk_per_trade),
        "risk_basis": "RESEARCH_SIMULATION_ONLY",
        "entry_conditions": [item.model_dump(mode="json") for item in strategy.entry],
        "invalidation": [item.model_dump(mode="json") for item in strategy.invalidation],
        "position_management": strategy.model_dump(mode="json")["position_management"],
        "pending_checks": [*strategy.sessions, *strategy.event_rules],
        "price_basis": "LATEST_CLOSED_CANDLE_INDICATIVE",
        "execution_authorized": False,
    }
    if strategy.trade_rules is None or len(candles) < 2:
        return {**result, "reason": "Price rules or candle evidence are unavailable"}
    if weekend_close(strategy.asset_class, now):
        return {
            **result,
            "status": "MARKET_CLOSED",
            "reason": "Market session is closed; refresh prices after reopening before entry",
        }
    latest = candles[-1]
    expires_at = latest.observed_at + timedelta(seconds=timeframe_seconds * 2)
    result.update(
        {
            "direction": strategy.trade_rules.direction,
            "entry_method": strategy.trade_rules.entry_method,
            "observed_at": latest.observed_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )
    if now >= expires_at or latest.observed_at > now:
        return {**result, "status": "STALE", "reason": "Refresh candle evidence before entry"}
    features = strategy_features(strategy, candles, len(candles) - 1)
    features.update(news_features(strategy.instruments[0], now, calendar))
    regime = regime_from_features(features)
    result.update({"regime": regime, "regime_key": regime_key(regime)})
    if not regime_matches(strategy.regimes, features):
        return {**result, "reason": "Current regime is outside the strategy's validated rules"}
    try:
        stop, targets = protection_levels(
            strategy.trade_rules, latest.close, features["volatility"], tick_size
        )
    except ValueError as exc:
        return {**result, "reason": str(exc)}
    signal = entry_matches(strategy, features)
    distance = abs(latest.close - stop)
    return {
        **result,
        "status": "SIGNAL" if signal else "WAIT",
        "reason": (
            "Entry conditions met; use the next bar open and recalculate protection at fill"
            if signal
            else "Wait for the strategy entry, confirmation and filter conditions"
        ),
        "entry": str(latest.close),
        "stop_loss": str(stop),
        "stop_distance": str(distance),
        "take_profits": [
            {
                "price": str(price),
                "reward_risk": str(abs(price - latest.close) / distance),
                "fraction": str(Decimal(1) / len(targets)),
            }
            for price in targets
        ],
    }
