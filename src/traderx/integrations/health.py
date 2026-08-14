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


def operational_components(
    *,
    base: dict[str, str],
    failed_jobs: int,
    stalled_jobs: int,
    queued_jobs: int,
    account_data_verified: bool,
    account_age_seconds: float | None,
) -> dict[str, str]:
    """Project worker, queue, and account-data evidence into explicit health components."""

    components = dict(base)
    components["jobs"] = "DEGRADED" if failed_jobs else "HEALTHY"
    components["workers"] = "DEGRADED" if stalled_jobs else "HEALTHY"
    components["queue"] = "DEGRADED" if queued_jobs > 100 else "HEALTHY"
    components["account_data"] = "HEALTHY" if account_data_verified else "DEGRADED"
    components["data_freshness"] = (
        "HEALTHY" if account_age_seconds is not None and account_age_seconds <= 90 else "DEGRADED"
    )
    return components
