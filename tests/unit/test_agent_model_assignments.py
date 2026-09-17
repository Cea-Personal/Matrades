from modules.agents.model_assignments import (
    AGENT_MODEL_ASSIGNMENTS,
    assignment_for,
    default_profile,
)
from modules.agents.registry import REQUIRED_AGENT_IDS


def test_every_required_agent_has_a_cost_aware_assignment():
    assert set(AGENT_MODEL_ASSIGNMENTS) == set(REQUIRED_AGENT_IDS)
    assert all(assignment.model for assignment in AGENT_MODEL_ASSIGNMENTS.values())
    assert all(
        assignment.reasoning_effort in {"low", "medium"}
        for assignment in AGENT_MODEL_ASSIGNMENTS.values()
    )


def test_strategy_synthesis_roles_use_balanced_model():
    for logical_id in ("orchestrator", "strategy_researcher", "strategy_assistant", "critic"):
        assert assignment_for(logical_id).model == "gpt-5.6-terra"
        assert assignment_for(logical_id).reasoning_effort == "medium"


def test_bounded_roles_use_cost_sensitive_model():
    for logical_id in REQUIRED_AGENT_IDS:
        if logical_id not in {
            "orchestrator",
            "strategy_researcher",
            "strategy_assistant",
            "critic",
        }:
            assert assignment_for(logical_id).model == "gpt-5.6-luna"
            assert assignment_for(logical_id).reasoning_effort == "low"


def test_role_profiles_are_stable_and_distinct_from_platform_default():
    profiles = [default_profile(logical_id) for logical_id in REQUIRED_AGENT_IDS]
    assert len({profile.id for profile in profiles}) == len(REQUIRED_AGENT_IDS)
    assert default_profile().id not in {profile.id for profile in profiles}
