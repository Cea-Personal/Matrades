from decimal import Decimal

from modules.backtesting.promotion import typed_promotable
from modules.strategies.compiler import compile_strategy
from packages.strategy_sdk.schema import Condition, StrategySpecification
from packages.strategy_sdk.taxonomy import Horizon, StrategyFamily, StrategyOrigin


def _spec() -> StrategySpecification:
    condition = Condition(feature="close", operator=">", value="1")
    return StrategySpecification(
        name="bounded",
        family=StrategyFamily.TREND,
        horizon=Horizon.INTRADAY,
        instruments=["EURUSD"],
        regimes=["TREND"],
        data_dependencies=["close"],
        entry=[condition],
        confirmations=[],
        filters=[],
        exit=[condition],
        invalidation=[],
        stop_loss=condition,
        take_profit=[condition],
        position_management={
            "move_to_break_even": False,
            "trailing_stop": False,
            "partial_take_profit": False,
        },
        sessions=["LONDON"],
        event_rules=[],
        risk_per_trade=Decimal("1"),
        parameters={},
        origin=StrategyOrigin.AI_GENERATED,
        evaluator_version="test",
    )


def test_compiled_strategy_is_signal_only_and_promotion_needs_all_gates() -> None:
    generated = compile_strategy(_spec()).generated_code
    assert "submit_order" not in generated.lower()
    assert typed_promotable({"backtest": True, "paper": False}, profile_complete=True) is False
