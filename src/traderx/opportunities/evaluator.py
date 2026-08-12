from __future__ import annotations

from dataclasses import dataclass

from traderx.opportunities.model import OpportunityState


@dataclass(frozen=True, slots=True)
class Evaluation:
    state: OpportunityState
    reason_codes: tuple[str, ...]


def evaluate_live_opportunity(
    *, active_market: bool, strategy_live_eligible: bool, data_verified: bool, signal_present: bool
) -> Evaluation:
    checks = (
        (active_market, "MARKET_NOT_ACTIVE"),
        (strategy_live_eligible, "STRATEGY_NOT_LIVE_ELIGIBLE"),
        (data_verified, "CRITICAL_DATA_UNAVAILABLE"),
        (signal_present, "NO_SIGNAL"),
    )
    failures = tuple(code for passed, code in checks if not passed)
    return Evaluation(
        OpportunityState.CANDIDATE if not failures else OpportunityState.NO_TRADE, failures
    )
