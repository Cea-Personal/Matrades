from enum import StrEnum

from modules.trading.broker_models import ManagementRecommendation, RecommendationAction
from modules.trading.legacy_compatibility import reject_new_write


class Hil3Action(StrEnum):
    APPROVE = "APPROVE"
    WAIT = "WAIT"
    REJECT = "REJECT"


def decide(
    recommendation: ManagementRecommendation,
    action: Hil3Action,
    policy_valid: bool,
    lifecycle_valid: bool = True,
) -> dict[str, object]:
    reject_new_write("HIL-3 decisions")
    if (
        recommendation.action != RecommendationAction.HOLD
        and action == Hil3Action.APPROVE
        and (not policy_valid or not lifecycle_valid)
    ):
        raise ValueError("recommendation no longer complies with policy or instrument lifecycle")
    return {
        "recommendation_id": recommendation.id,
        "decision": action,
        "broker_mutated": False,
        "manual_execution_required": action == Hil3Action.APPROVE,
    }
