from __future__ import annotations

from modules.agents.models import AgentDefinition, ModelProfile


class ProfileCatalog:
    def __init__(self) -> None:
        self.profiles: dict = {}

    def add(self, profile: ModelProfile) -> None:
        for fallback_id in profile.fallback_profile_ids:
            fallback = self.profiles.get(fallback_id)
            if fallback is None or fallback.runtime != profile.runtime:
                raise ValueError("fallbacks must exist and remain in the selected runtime")
        self.profiles[profile.id] = profile

    def activate_for(
        self, agent: AgentDefinition, profile_id: object, required_capabilities: set[str]
    ) -> AgentDefinition:
        profile = self.profiles.get(profile_id)
        if profile is None or not profile.active:
            raise ValueError("profile is unavailable")
        if not required_capabilities <= profile.capabilities:
            raise ValueError("profile lacks required capabilities")
        return agent.model_copy(update={"runtime": profile.runtime, "profile_id": profile.id})
