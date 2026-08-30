from packages.strategy_sdk.taxonomy import StrategyOrigin


def test_strategy_origin_is_limited_to_ai_modes() -> None:
    assert {item.value for item in StrategyOrigin} == {"AI_GENERATED", "AI_ASSISTED"}
