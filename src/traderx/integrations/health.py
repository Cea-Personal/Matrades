from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.integrations.registry import approved_provider


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


def provider_health_state(
    integration: Integration,
    latest: IntegrationHealthObservation | None = None,
    *,
    now: datetime | None = None,
    maximum_age_seconds: int = 300,
) -> tuple[str, tuple[str, ...]]:
    """Aggregate lifecycle, entitlement, qualification, and freshness fail-closed."""

    definition = approved_provider(integration.provider)
    if integration.state == "DISABLED":
        return "DISABLED", tuple(sorted(integration.capabilities))
    if integration.state in {"FAILED", "REMOVED"}:
        return "FAILED", tuple(sorted(integration.capabilities))
    if definition.entitlement_required and integration.entitlement_status != "VERIFIED":
        return "DEGRADED", tuple(sorted(integration.capabilities))
    if latest is not None and latest.status == "FAILED":
        return "FAILED", tuple(sorted(latest.affected_capabilities or integration.capabilities))
    if now is not None and latest is not None:
        observed_at = latest.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=now.tzinfo)
        if (now - observed_at).total_seconds() > maximum_age_seconds:
            return "DEGRADED", tuple(sorted(integration.capabilities))
    if integration.state == "HEALTHY" and latest is not None and latest.status == "HEALTHY":
        return "HEALTHY", ()
    return "DEGRADED", tuple(sorted(integration.capabilities))
