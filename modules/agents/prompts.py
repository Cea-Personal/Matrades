from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSet:
    system: str | None = None
    user: str | None = None
    version: str = "v1"


@dataclass(frozen=True)
class ResolvedPrompts:
    system: str
    user: str
    system_source: str
    user_source: str


def resolve_prompts(
    agent: PromptSet, orchestrator: PromptSet, platform: PromptSet
) -> ResolvedPrompts:
    system, system_source = (
        (agent.system, "agent")
        if agent.system is not None
        else (orchestrator.system, "orchestrator")
        if orchestrator.system is not None
        else (platform.system, "platform")
    )
    user, user_source = (
        (agent.user, "agent")
        if agent.user is not None
        else (orchestrator.user, "orchestrator")
        if orchestrator.user is not None
        else (platform.user, "platform")
    )
    if system is None or user is None:
        raise ValueError("platform prompts must complete both independent chains")
    return ResolvedPrompts(system, user, system_source, user_source)
