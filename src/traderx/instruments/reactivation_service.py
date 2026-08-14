from __future__ import annotations

from dataclasses import dataclass

from traderx.instruments.reactivation import IncrementalRefreshPlan
from traderx.strategies.staleness import RevalidationPlan


@dataclass(frozen=True, slots=True)
class ReactivationOutcome:
    state: str
    plan: RevalidationPlan
    preserved_knowledge: dict[str, int]
    missing_interval_count: int
    automatically_activated: bool = False


def begin_reactivation(
    plan: RevalidationPlan,
    *,
    preserved_knowledge: dict[str, int] | None = None,
    refresh_plan: IncrementalRefreshPlan | None = None,
) -> ReactivationOutcome:
    """No reactivation path returns ACTIVE; approval remains an explicit later command."""
    return ReactivationOutcome(
        "AWAITING_HUMAN_APPROVAL" if not plan.steps else "REVALIDATION_REQUIRED",
        plan,
        dict(preserved_knowledge or {}),
        len(refresh_plan.missing) if refresh_plan else 0,
    )
