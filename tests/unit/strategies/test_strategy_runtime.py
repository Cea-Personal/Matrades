from decimal import Decimal

from traderx.strategies.compiler import compile_strategy
from traderx.strategies.runtime import evaluate
from traderx.strategies.schema import StrategyDefinition


def definition() -> StrategyDefinition:
    return StrategyDefinition(
        "TREND",
        ("1h",),
        ({"field": "close", "operator": ">", "value": Decimal("100")},),
        stop={"type": "price"},
        target={"type": "rr"},
        invalidation={"type": "price"},
    )


def test_compilation_is_deterministic_and_runtime_has_no_hidden_state() -> None:
    compiled = compile_strategy(definition())
    assert compiled.definition_hash == compile_strategy(definition()).definition_hash
    assert (
        evaluate(
            compiled, {"regime": "TREND", "close": Decimal("101")}, portfolio_capacity=1
        ).action
        == "CANDIDATE"
    )
    assert (
        evaluate(compiled, {"regime": "TREND", "close": Decimal("99")}, portfolio_capacity=1).action
        == "NO_TRADE"
    )
