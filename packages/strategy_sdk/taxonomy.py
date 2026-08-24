from enum import StrEnum


class StrategyOrigin(StrEnum):
    AI_GENERATED = "AI_GENERATED"
    AI_ASSISTED = "AI_ASSISTED"
    HUMAN_CREATED = "HUMAN_CREATED"
    IMPORTED = "IMPORTED"


class StrategyFamily(StrEnum):
    TREND = "TREND"
    MEAN_REVERSION = "MEAN_REVERSION"
    BREAKOUT = "BREAKOUT"
    LIQUIDITY = "LIQUIDITY"
    EVENT = "EVENT"


class Horizon(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    POSITION = "POSITION"


class SignalType(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    INVALIDATION = "INVALIDATION"
    FILTER = "FILTER"
