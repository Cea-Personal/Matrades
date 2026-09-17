"""Cost-aware model defaults for the protected Matrades logical agents.

These are recommendations, not hard overrides: an explicitly configured
``ModelProfile`` always wins.  Keeping the defaults here gives the API and the
isolated worker one source of truth for both execution and display.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from modules.agents.models import ModelProfile, RuntimeType


@dataclass(frozen=True)
class AgentModelAssignment:
    model: str
    reasoning_effort: str
    tier: str
    rationale: str


_TERRA = AgentModelAssignment(
    model="gpt-5.6-terra",
    reasoning_effort="medium",
    tier="balanced",
    rationale=(
        "Needs multi-step synthesis and structured judgment, but not flagship-tier reasoning."
    ),
)
_LUNA = AgentModelAssignment(
    model="gpt-5.6-luna",
    reasoning_effort="low",
    tier="cost-sensitive",
    rationale=(
        "Bounded, repeatable evidence extraction or monitoring work does not justify a larger model."
    ),
)


AGENT_MODEL_ASSIGNMENTS: dict[str, AgentModelAssignment] = {
    "orchestrator": _TERRA,
    "strategy_researcher": _TERRA,
    "strategy_assistant": _TERRA,
    "critic": _TERRA,
    "forex_research": _LUNA,
    "metals_research": _LUNA,
    "crypto_research": _LUNA,
    "stocks_research": _LUNA,
    "technical_analyst": _LUNA,
    "fundamental_analyst": _LUNA,
    "sentiment_analyst": _LUNA,
    "regime_analyst": _LUNA,
    "strategy_selector": _LUNA,
    "trade_monitor": _LUNA,
    "journal": _LUNA,
    "performance": _LUNA,
    "knowledge_assistant": _LUNA,
}


def assignment_for(logical_id: str) -> AgentModelAssignment:
    """Return the recommendation for a known role, with a safe balanced fallback."""

    return AGENT_MODEL_ASSIGNMENTS.get(logical_id, _TERRA)


def default_profile(
    logical_id: str | None = None,
    *,
    fallback_model: str = "gpt-5.6-terra",
) -> ModelProfile:
    """Build a deterministic unconfigured profile for a role.

    The generic profile keeps the runtime setting as its model. Role-specific
    profiles use the curated assignment so each unconfigured agent is routed
    independently. ``fallback_model`` is retained for deployments that change
    the platform-wide default in settings.
    """

    if logical_id is None:
        model = fallback_model
        profile_id = uuid5(NAMESPACE_URL, "matrades:codex-default")
        name = "Matrades Codex default"
        parameters = {"assignment": "platform_default"}
    else:
        assignment = assignment_for(logical_id)
        model = assignment.model
        profile_id = uuid5(NAMESPACE_URL, f"matrades:codex-default:{logical_id}")
        name = f"Matrades recommended — {logical_id}"
        parameters = {
            "assignment": "recommended",
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
