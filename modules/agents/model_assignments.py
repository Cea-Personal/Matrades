"""Native files supply API and worker defaults; saved profiles override them."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from modules.agents.models import ModelProfile, RuntimeType
from modules.agents.native_config import load_native_agent
from modules.agents.registry import REQUIRED_AGENT_IDS


@dataclass(frozen=True)
class AgentModelAssignment:
    model: str
    reasoning_effort: str
    tier: str
    rationale: str


def assignment_for(logical_id: str) -> AgentModelAssignment:
    config = load_native_agent(logical_id)
    return AgentModelAssignment(
        model=config["model"],
        reasoning_effort=config["model_reasoning_effort"],
        tier="native-agent",
        rationale=f"Configured in .codex/agents/{logical_id}.toml",
    )


class _NativeAssignments(Mapping[str, AgentModelAssignment]):
    """Compatibility mapping that resolves values at access, not startup."""

    def __getitem__(self, key: str) -> AgentModelAssignment:
        if key not in REQUIRED_AGENT_IDS:
            raise KeyError(key)
        return assignment_for(key)

    def __iter__(self) -> Iterator[str]:
        return iter(REQUIRED_AGENT_IDS)

    def __len__(self) -> int:
        return len(REQUIRED_AGENT_IDS)


AGENT_MODEL_ASSIGNMENTS = _NativeAssignments()


def default_profile(
    logical_id: str | None = None,
    *,
    fallback_model: str = "gpt-5.6-terra",
) -> ModelProfile:
    """Read the role file, retaining stable IDs and the generic platform fallback."""

    if logical_id is None:
        model = fallback_model
        profile_id = uuid5(NAMESPACE_URL, "matrades:codex-default")
        name = "Matrades Codex default"
        parameters = {"assignment": "platform_default"}
    else:
        assignment = assignment_for(logical_id)
        model = assignment.model
        profile_id = uuid5(NAMESPACE_URL, f"matrades:codex-default:{logical_id}")
        name = f"Matrades native agent — {logical_id}"
        parameters = {
            "assignment": "native_agent",
            "source_file": f".codex/agents/{logical_id}.toml",
            "reasoning_effort": assignment.reasoning_effort,
            "tier": assignment.tier,
            "rationale": assignment.rationale,
        }
    return ModelProfile(
        id=profile_id,
        name=name,
        runtime=RuntimeType.CODEX_APP_SERVER,
        provider="openai",
        model=model,
        parameters=parameters,
        capabilities={"structured_output", "reasoning"},
    )


def recommended_profile_id(logical_id: str) -> UUID:
    return default_profile(logical_id).id
