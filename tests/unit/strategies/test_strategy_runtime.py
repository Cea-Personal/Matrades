from datetime import UTC, datetime
from decimal import Decimal

from traderx.strategies.compiler import compile_strategy
from traderx.strategies.runtime import RuntimeDependencies, StrategyRuntime, evaluate
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


def test_runtime_uses_only_injected_clock_calendar_data_portfolio_and_execution() -> None:
    instant = datetime(2026, 8, 14, 12, tzinfo=UTC)

    class Clock:
        def now(self) -> datetime:
            return instant

    class Calendar:
        def is_open(self, instrument_id: str, at: datetime) -> bool:
            return instrument_id == "EURUSD" and at == instant

    class Data:
        def facts(self, instrument_id: str, at: datetime) -> dict[str, object]:
            return {"regime": "TREND", "close": Decimal("101")}

    class Portfolio:
        def capacity(self, instrument_id: str, at: datetime) -> int:
            return 1

    class Execution:
        def executable(self, instrument_id: str, at: datetime) -> bool:
            return True

    runtime = StrategyRuntime(
        compile_strategy(definition()),
        RuntimeDependencies(Clock(), Calendar(), Data(), Portfolio(), Execution()),
    )
    first = runtime.evaluate("EURUSD")
    assert first == runtime.evaluate("EURUSD")
    assert first.evaluated_at == instant
    assert first.trace[0]["matched"] is True
