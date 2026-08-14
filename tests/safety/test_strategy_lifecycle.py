import pytest

from traderx.shared.types import InvalidTransition
from traderx.strategies.lifecycle import VersionState, immutable_edit, transition
from traderx.strategies.model import StrategyLifecycle


def test_lifecycle_requires_evidence_and_edits_make_a_new_draft_version() -> None:
    state = VersionState(1, "a", StrategyLifecycle.DRAFT)
    validating = transition(state, StrategyLifecycle.VALIDATING, evidence_passed=False)
    with pytest.raises(InvalidTransition):
        transition(validating, StrategyLifecycle.QUALIFIED, evidence_passed=False)
    assert immutable_edit(state, "b").version == 2


def test_lifecycle_rejects_skips_and_retired_versions_are_terminal() -> None:
    with pytest.raises(InvalidTransition):
        transition(
            VersionState(1, "a", StrategyLifecycle.DRAFT),
            StrategyLifecycle.LIVE,
            evidence_passed=True,
        )
    with pytest.raises(InvalidTransition):
        transition(
            VersionState(4, "retired", StrategyLifecycle.RETIRED),
            StrategyLifecycle.DRAFT,
            evidence_passed=True,
        )
