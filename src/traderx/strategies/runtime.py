from __future__ import annotations

from dataclasses import dataclass

from traderx.strategies.compiler import CompiledStrategy


@dataclass(frozen=True, slots=True)
class StrategySignal:
    action: str
    reason_codes: tuple[str, ...]


def evaluate(
    compiled: CompiledStrategy, facts: dict[str, object], *, portfolio_capacity: int
) -> StrategySignal:
    if portfolio_capacity <= 0:
        return StrategySignal("NO_TRADE", ("PORTFOLIO_CAPACITY_EXHAUSTED",))
    if facts.get("regime") != compiled.definition.regime:
        return StrategySignal("NO_TRADE", ("REGIME_MISMATCH",))
    for condition in compiled.definition.conditions:
        actual = facts.get(str(condition["field"]))
        expected = condition["value"]
        operator = condition["operator"]
        matches = {
            "==": actual == expected,
            ">": actual is not None and actual > expected,
            "<": actual is not None and actual < expected,
        }.get(operator, False)
        if not matches:
            return StrategySignal("NO_TRADE", ("CONDITION_NOT_MET",))
    return StrategySignal("CANDIDATE", ("ALL_RULES_MET",))
