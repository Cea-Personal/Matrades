from modules.performance.strategy_health import evaluate


def test_degradation_creates_controlled_action_without_mutation():
    result = evaluate({"expectancy": -1}, "active-v7")
    assert result["action"] == "RESEARCH_REQUEST"
    assert result["active_version"] == "active-v7"
    assert result["active_mutated"] == "false"
