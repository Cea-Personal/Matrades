"""Evidence-timestamped indicative trade levels for a researched strategy."""

from datetime import datetime, timedelta
from decimal import Decimal

from modules.backtesting.engine import BacktestCandle
from modules.strategies.signals import candle_features, entry_matches, protection_levels
from packages.strategy_sdk.schema import StrategySpecification


def build_strategy_setup(
    strategy: StrategySpecification,
    candles: list[BacktestCandle],
    *,
    now: datetime,
    timeframe_seconds: int,
    tick_size: Decimal | None = None,
) -> dict:
    result = {
        "status": "WAIT",
        "instrument": strategy.instruments[0],
        "entry": None,
        "stop_loss": None,
        "take_profits": [],
        "risk_per_trade_percent": str(strategy.risk_per_trade),
        "entry_conditions": [item.model_dump(mode="json") for item in strategy.entry],
        "invalidation": [item.model_dump(mode="json") for item in strategy.invalidation],
        "position_management": strategy.model_dump(mode="json")["position_management"],
        "pending_checks": [*strategy.sessions, *strategy.event_rules],
        "price_basis": "LATEST_CLOSED_CANDLE_INDICATIVE",
        "execution_authorized": False,
    }
    if strategy.trade_rules is None or len(candles) < 2:
        return {**result, "reason": "Price rules or candle evidence are unavailable"}
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
    features = candle_features(candles, len(candles) - 1)
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
