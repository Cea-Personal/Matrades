from modules.performance.models import HealthAction


def evaluate(metrics: dict[str, float], active_version: str) -> dict[str, str]:
    action = (
        HealthAction.SUSPENSION_REVIEW
        if metrics.get("drawdown", 0) > 0.15
        else HealthAction.RESEARCH_REQUEST
        if metrics.get("expectancy", 0) < 0
        else HealthAction.NONE
    )
    return {"active_version": active_version, "action": action, "active_mutated": "false"}
