from packages.strategy_sdk.taxonomy import StrategyFamily

INITIAL_PATTERNS = {
    StrategyFamily.TREND: ("higher_highs", "pullback"),
    StrategyFamily.MEAN_REVERSION: ("range_extreme", "reversion_trigger"),
    StrategyFamily.BREAKOUT: ("compression", "confirmed_break"),
    StrategyFamily.LIQUIDITY: ("sweep", "reclaim"),
}
