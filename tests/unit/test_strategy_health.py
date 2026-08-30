from modules.performance.models import HealthAction
from modules.performance.strategy_health import evaluate_health


def test_strategy_health_creates_work_without_mutating_active_version() -> None:
    result = evaluate_health({"drawdown": 0.2, "expectancy": -1}, "strategy-v1")
    assert result.action is HealthAction.SUSPENSION_REVIEW
    assert result.active_mutated is False
    assert result.strategy_version_id == "strategy-v1"
