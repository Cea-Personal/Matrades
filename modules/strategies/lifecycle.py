from enum import StrEnum


class StrategyState(StrEnum):
    DRAFT = "DRAFT"
    SPECIFIED = "SPECIFIED"
    IMPLEMENTED = "IMPLEMENTED"
    BACKTESTING = "BACKTESTING"
    VALIDATING = "VALIDATING"
    PAPER_TRADING = "PAPER_TRADING"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


ALLOWED = {
    StrategyState.DRAFT: {StrategyState.SPECIFIED},
    StrategyState.SPECIFIED: {StrategyState.IMPLEMENTED},
    StrategyState.IMPLEMENTED: {StrategyState.BACKTESTING},
    StrategyState.BACKTESTING: {StrategyState.VALIDATING},
    StrategyState.VALIDATING: {StrategyState.PAPER_TRADING},
    StrategyState.PAPER_TRADING: {StrategyState.APPROVED},
    StrategyState.APPROVED: {StrategyState.ACTIVE},
    StrategyState.ACTIVE: {StrategyState.DEGRADED, StrategyState.SUSPENDED, StrategyState.RETIRED},
    StrategyState.DEGRADED: {StrategyState.ACTIVE, StrategyState.SUSPENDED, StrategyState.RETIRED},
    StrategyState.SUSPENDED: {StrategyState.ACTIVE, StrategyState.RETIRED},
}


def transition(current: StrategyState, target: StrategyState) -> StrategyState:
    if target not in ALLOWED.get(current, set()):
        raise ValueError("illegal strategy lifecycle transition")
    return target
