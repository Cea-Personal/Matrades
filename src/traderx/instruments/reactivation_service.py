from __future__ import annotations

from dataclasses import dataclass

from traderx.strategies.staleness import RevalidationPlan


@dataclass(frozen=True, slots=True)
class ReactivationOutcome:
    state: str
    plan: RevalidationPlan


def begin_reactivation(plan: RevalidationPlan) -> ReactivationOutcome:
    """No reactivation path returns ACTIVE; approval remains an explicit later command."""
    return ReactivationOutcome(
        "AWAITING_HUMAN_APPROVAL" if not plan.steps else "REVALIDATION_REQUIRED", plan
    )
