from __future__ import annotations

from dataclasses import dataclass, replace

from traderx.shared.types import InvalidTransition
from traderx.strategies.model import StrategyLifecycle

_ALLOWED: dict[StrategyLifecycle, set[StrategyLifecycle]] = {
    StrategyLifecycle.DRAFT: {StrategyLifecycle.VALIDATING, StrategyLifecycle.RETIRED},
    StrategyLifecycle.VALIDATING: {
        StrategyLifecycle.QUALIFIED,
        StrategyLifecycle.REJECTED,
        StrategyLifecycle.DRAFT,
    },
    StrategyLifecycle.QUALIFIED: {StrategyLifecycle.PAPER, StrategyLifecycle.RETIRED},
    StrategyLifecycle.PAPER: {StrategyLifecycle.AWAITING_APPROVAL, StrategyLifecycle.REJECTED},
    StrategyLifecycle.AWAITING_APPROVAL: {
        StrategyLifecycle.LIVE_ELIGIBLE,
        StrategyLifecycle.REJECTED,
    },
    StrategyLifecycle.LIVE_ELIGIBLE: {StrategyLifecycle.RETIRED},
    StrategyLifecycle.REJECTED: {StrategyLifecycle.DRAFT, StrategyLifecycle.RETIRED},
    StrategyLifecycle.RETIRED: set(),
}


@dataclass(frozen=True, slots=True)
class VersionState:
    version: int
    definition_hash: str
    lifecycle: StrategyLifecycle


def transition(
    state: VersionState, target: StrategyLifecycle, *, evidence_passed: bool
) -> VersionState:
    if target not in _ALLOWED[state.lifecycle]:
        raise InvalidTransition(f"cannot transition strategy from {state.lifecycle} to {target}")
    if (
        target
        in {
            StrategyLifecycle.QUALIFIED,
            StrategyLifecycle.AWAITING_APPROVAL,
            StrategyLifecycle.LIVE_ELIGIBLE,
        }
        and not evidence_passed
    ):
        raise InvalidTransition("required validation evidence has not passed")
    return replace(state, lifecycle=target)


def immutable_edit(state: VersionState, definition_hash: str) -> VersionState:
    if definition_hash == state.definition_hash:
        raise ValueError("an immutable edit must change the strategy definition")
    return VersionState(state.version + 1, definition_hash, StrategyLifecycle.DRAFT)
