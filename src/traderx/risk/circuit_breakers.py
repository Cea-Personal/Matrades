from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class CircuitBreakerState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLEARED = "CLEARED"


@dataclass(frozen=True, slots=True)
class BreakerResult:
    state: CircuitBreakerState
    reason: str | None
    occurred_at: datetime


def trip_if_critical(*, equity: Decimal | None, data_fresh: bool, now: datetime) -> BreakerResult:
    if equity is None:
        return BreakerResult(CircuitBreakerState.TRIPPED, "UNKNOWN_EQUITY", now)
    if not data_fresh:
        return BreakerResult(CircuitBreakerState.TRIPPED, "STALE_CRITICAL_DATA", now)
    return BreakerResult(CircuitBreakerState.ARMED, None, now)


def acknowledge(result: BreakerResult, now: datetime) -> BreakerResult:
    if result.state != CircuitBreakerState.TRIPPED:
        raise ValueError("only a tripped circuit breaker can be acknowledged")
    return BreakerResult(CircuitBreakerState.ACKNOWLEDGED, result.reason, now)


def clear(result: BreakerResult, *, critical_data_healthy: bool, now: datetime) -> BreakerResult:
    if not critical_data_healthy:
        raise ValueError("a circuit breaker cannot clear while critical data is unhealthy")
    if result.state not in {CircuitBreakerState.TRIPPED, CircuitBreakerState.ACKNOWLEDGED}:
        raise ValueError("only a tripped or acknowledged circuit breaker can clear")
    return BreakerResult(CircuitBreakerState.CLEARED, None, now)
