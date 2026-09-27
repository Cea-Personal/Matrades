import tomllib
from pathlib import Path

import pytest

from modules.agents.model_assignments import (
    AGENT_MODEL_ASSIGNMENTS,
    assignment_for,
    default_profile,
)
from modules.agents.native_config import REASONING_EFFORTS
from modules.agents.registry import REQUIRED_AGENT_IDS


def test_every_required_agent_has_a_valid_native_assignment():
    assert set(AGENT_MODEL_ASSIGNMENTS) == set(REQUIRED_AGENT_IDS)
    assert all(assignment.model for assignment in AGENT_MODEL_ASSIGNMENTS.values())
    assert all(
        assignment.reasoning_effort in REASONING_EFFORTS
        for assignment in AGENT_MODEL_ASSIGNMENTS.values()
    )


@pytest.mark.parametrize("effort", sorted(REASONING_EFFORTS))
def test_native_assignment_preserves_each_supported_reasoning_effort(monkeypatch, tmp_path, effort):
    from modules.agents import native_config

    monkeypatch.setattr(native_config, "NATIVE_AGENTS_DIR", tmp_path)
    (tmp_path / "critic.toml").write_text(
        'name = "critic"\nmodel = "configured-model"\n'
        f'model_reasoning_effort = "{effort}"\n'
        'description = "Review"\ndeveloper_instructions = "Review only"\n'
        'sandbox_mode = "read-only"\n'
    )
    assignment = assignment_for("critic")
    profile = default_profile("critic")
    assert assignment.model == profile.model == "configured-model"
    assert assignment.reasoning_effort == profile.parameters["reasoning_effort"] == effort


@pytest.mark.parametrize("effort", ["", "unsupported", "HIGH"])
def test_native_assignment_rejects_unsupported_reasoning_effort(monkeypatch, tmp_path, effort):
    from modules.agents import native_config

    monkeypatch.setattr(native_config, "NATIVE_AGENTS_DIR", tmp_path)
    (tmp_path / "critic.toml").write_text(
        'name = "critic"\nmodel = "configured-model"\n'
        f'model_reasoning_effort = "{effort}"\n'
        'description = "Review"\ndeveloper_instructions = "Review only"\n'
        'sandbox_mode = "read-only"\n'
    )
    with pytest.raises(ValueError, match="invalid reasoning effort"):
        default_profile("critic")


def test_every_role_uses_its_current_native_file():
    directory = Path(__file__).resolve().parents[2] / ".codex" / "agents"
    for logical_id in REQUIRED_AGENT_IDS:
        native = tomllib.loads((directory / f"{logical_id}.toml").read_text())
        assert assignment_for(logical_id).model == native["model"]
        assert assignment_for(logical_id).reasoning_effort == native["model_reasoning_effort"]
        assert default_profile(logical_id).parameters["assignment"] == "native_agent"


def test_native_edits_are_seen_without_restarting_api(monkeypatch, tmp_path):
    from modules.agents import native_config

    monkeypatch.setattr(native_config, "NATIVE_AGENTS_DIR", tmp_path)
    source = (
        'name = "critic"\nmodel = "model-one"\nmodel_reasoning_effort = "low"\n'
        'description = "Review"\ndeveloper_instructions = "Review only"\n'
        'sandbox_mode = "read-only"\n'
    )
    path = tmp_path / "critic.toml"
    path.write_text(source)
    before = default_profile("critic")
    path.write_text(source.replace("model-one", "model-two").replace('"low"', '"high"'))
    after = default_profile("critic")
    assert before.id == after.id
    assert after.model == "model-two"
    assert AGENT_MODEL_ASSIGNMENTS["critic"].reasoning_effort == "high"


@pytest.mark.parametrize("source", [None, "not valid toml", 'name = "other"'])
def test_missing_or_invalid_files_do_not_silently_use_old_defaults(monkeypatch, tmp_path, source):
    from modules.agents import native_config

    monkeypatch.setattr(native_config, "NATIVE_AGENTS_DIR", tmp_path)
    if source is not None:
        (tmp_path / "critic.toml").write_text(source)
    with pytest.raises(ValueError, match="Native agent"):
        default_profile("critic")


def test_native_role_rejects_path_traversal():
    with pytest.raises(ValueError, match="invalid native agent role"):
        assignment_for("../../auth")


def test_role_profiles_are_stable_and_distinct_from_platform_default():
    profiles = [default_profile(logical_id) for logical_id in REQUIRED_AGENT_IDS]
    assert len({profile.id for profile in profiles}) == len(REQUIRED_AGENT_IDS)
    assert default_profile().id not in {profile.id for profile in profiles}
