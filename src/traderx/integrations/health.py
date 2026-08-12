from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemHealth:
    status: str
    components: dict[str, str]
    safety_impact: tuple[str, ...]


def aggregate_health(components: dict[str, str]) -> SystemHealth:
    failed = tuple(name for name, value in components.items() if value != "HEALTHY")
    return SystemHealth("HEALTHY" if not failed else "DEGRADED", components, failed)
