from pydantic import BaseModel, Field

from modules.performance.models import HealthAction


class StrategyHealthWork(BaseModel):
    strategy_version_id: str
    action: HealthAction
    active_mutated: bool = False
    reason: str = Field(min_length=1)


def evaluate(metrics: dict[str, float], active_version: str) -> dict[str, str]:
    action = (
        HealthAction.SUSPENSION_REVIEW
        if metrics.get("drawdown", 0) > 0.15
        else HealthAction.RESEARCH_REQUEST
        if metrics.get("expectancy", 0) < 0
        else HealthAction.NONE
    )
    return {"active_version": active_version, "action": action, "active_mutated": "false"}


def evaluate_health(metrics: dict[str, float], active_version: str) -> StrategyHealthWork:
    result = evaluate(metrics, active_version)
    action = HealthAction(result["action"])
    reason = (
        "drawdown exceeded the suspension-review threshold"
        if action is HealthAction.SUSPENSION_REVIEW
        else "expectancy is negative; research request created"
        if action is HealthAction.RESEARCH_REQUEST
        else "health metrics remain within configured bounds"
    )
    return StrategyHealthWork(
        strategy_version_id=active_version,
        action=action,
        active_mutated=False,
        reason=reason,
    )
