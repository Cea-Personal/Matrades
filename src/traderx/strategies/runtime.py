from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from traderx.strategies.compiler import CompiledStrategy


@dataclass(frozen=True, slots=True)
class StrategySignal:
    action: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime | None = None
    trace: tuple[dict[str, object], ...] = ()


class RuntimeState(StrEnum):
    DORMANT = "DORMANT"
    CANDIDATE = "CANDIDATE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class RuntimeClock(Protocol):
    def now(self) -> datetime: ...


class RuntimeCalendar(Protocol):
    def is_open(self, instrument_id: str, at: datetime) -> bool: ...


class RuntimeData(Protocol):
    def facts(self, instrument_id: str, at: datetime) -> dict[str, object]: ...


class RuntimePortfolio(Protocol):
    def capacity(self, instrument_id: str, at: datetime) -> int: ...


class RuntimeExecution(Protocol):
    def executable(self, instrument_id: str, at: datetime) -> bool: ...


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    clock: RuntimeClock
    calendar: RuntimeCalendar
    data: RuntimeData
    portfolio: RuntimePortfolio
    execution: RuntimeExecution


class StrategyRuntime:
    """Pure rule evaluation with every changing dependency supplied by the caller."""

    def __init__(self, compiled: CompiledStrategy, dependencies: RuntimeDependencies) -> None:
        self._compiled = compiled
        self._dependencies = dependencies

    def evaluate(self, instrument_id: str) -> StrategySignal:
        at = self._dependencies.clock.now()
        if not self._dependencies.calendar.is_open(instrument_id, at):
            return StrategySignal("NO_TRADE", ("MARKET_CLOSED",), at)
        if not self._dependencies.execution.executable(instrument_id, at):
            return StrategySignal("NO_TRADE", ("EXECUTION_UNAVAILABLE",), at)
        signal = evaluate(
            self._compiled,
            self._dependencies.data.facts(instrument_id, at),
            portfolio_capacity=self._dependencies.portfolio.capacity(instrument_id, at),
        )
        return StrategySignal(signal.action, signal.reason_codes, at, signal.trace)


def evaluate(
    compiled: CompiledStrategy, facts: dict[str, object], *, portfolio_capacity: int
) -> StrategySignal:
    trace: list[dict[str, object]] = []
    if portfolio_capacity <= 0:
        return StrategySignal("NO_TRADE", ("PORTFOLIO_CAPACITY_EXHAUSTED",))
    if facts.get("regime") != compiled.definition.regime:
        return StrategySignal("NO_TRADE", ("REGIME_MISMATCH",))
    for index, condition in enumerate((*compiled.definition.filters, *compiled.definition.conditions)):
        actual = facts.get(str(condition["field"]))
        expected = condition["value"]
        operator = condition["operator"]
        matches = {
            "==": actual == expected,
            ">": actual is not None and actual > expected,
            "<": actual is not None and actual < expected,
            ">=": actual is not None and actual >= expected,
            "<=": actual is not None and actual <= expected,
            "!=": actual != expected,
        }.get(operator, False)
        trace.append(
            {
                "index": index,
                "field": condition["field"],
                "operator": operator,
                "expected": expected,
                "actual": actual,
                "matched": matches,
            }
        )
        if not matches:
            code = "FILTER_NOT_MET" if index < len(compiled.definition.filters) else "CONDITION_NOT_MET"
            return StrategySignal("NO_TRADE", (code,), trace=tuple(trace))
    return StrategySignal("CANDIDATE", ("ALL_RULES_MET",), trace=tuple(trace))
