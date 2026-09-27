"""Resolve owner-scoped agent configuration identically in the API and worker."""

from uuid import UUID

from modules.agents.model_assignments import default_profile
from modules.agents.models import AgentDefinition, ModelProfile
from modules.agents.registry import REQUIRED_AGENT_IDS
from packages.shared.config import get_settings
from packages.shared.store import ResourceStore


def native_profile(logical_id: str | None = None) -> ModelProfile:
    return default_profile(logical_id, fallback_model=get_settings().default_codex_model)


async def load_profiles(store: ResourceStore, owner_id: UUID) -> dict[UUID, ModelProfile]:
    default = native_profile()
    profiles = {default.id: default}
    for logical_id in REQUIRED_AGENT_IDS:
        profile = native_profile(logical_id)
        profiles[profile.id] = profile
    for item in await store.list("agent_profile", owner_id):
        profile = ModelProfile.model_validate(item.data)
        profiles[profile.id] = profile.model_copy(
            update={"parameters": {**profile.parameters, "assignment": "agent_profile"}}
        )
    return profiles


async def load_agents(store: ResourceStore, owner_id: UUID) -> dict[str, AgentDefinition]:
    agents = {
        logical_id: AgentDefinition(logical_id=logical_id) for logical_id in REQUIRED_AGENT_IDS
    }
    for item in await store.list("agent_configuration", owner_id):
        agent = AgentDefinition.model_validate(item.data)
        agents[agent.logical_id] = agent
    return agents
