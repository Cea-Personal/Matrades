from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ComponentHealth:
    component: str
    state: HealthState
    fresh: bool
    last_success_at: datetime | None = None
    error: str | None = None


def aggregate(items: list[ComponentHealth]) -> HealthState:
    states = {item.state for item in items}
    return (
        HealthState.UNAVAILABLE
        if HealthState.UNAVAILABLE in states
        else HealthState.DEGRADED
        if HealthState.DEGRADED in states or any(not item.fresh for item in items)
        else HealthState.HEALTHY
    )
