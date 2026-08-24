from __future__ import annotations

from typing import Annotated, Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.agents.models import AgentDefinition, ModelProfile, RuntimeType
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import PromptSet, resolve_prompts
from modules.agents.registry import REQUIRED_AGENT_IDS
from modules.agents.runtime import AgentRuntimeRouter
from modules.identity.authorization import Actor, Role
from packages.shared.config import get_settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/agents", tags=["Agents"])
runtime_router = AgentRuntimeRouter.from_settings()


class AgentTestInput(BaseModel):
    input: dict[str, Any] = {}


def _default_profile() -> ModelProfile:
    return ModelProfile(
        id=uuid5(NAMESPACE_URL, "matrades:codex-default"),
        name="Matrades Codex default",
        runtime=RuntimeType.CODEX_APP_SERVER,
        provider="openai",
        model=get_settings().default_codex_model,
        capabilities={"structured_output", "reasoning"},
    )


async def _profiles(store: ResourceStore, owner_id: UUID) -> dict[UUID, ModelProfile]:
    default = _default_profile()
    result = {default.id: default}
    for item in await store.list("agent_profile", owner_id):
        profile = ModelProfile.model_validate(item.data)
        result[profile.id] = profile
    return result


async def _agents(store: ResourceStore, owner_id: UUID) -> dict[str, AgentDefinition]:
    result = {
        logical_id: AgentDefinition(logical_id=logical_id)
        for logical_id in REQUIRED_AGENT_IDS
    }
    for item in await store.list("agent_configuration", owner_id):
        agent = AgentDefinition.model_validate(item.data)
        result[agent.logical_id] = agent
    return result


@router.get("/registry")
async def list_agents(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agents = await _agents(ResourceStore(db), actor.owner_id)
    return [agents[logical_id].model_dump(mode="json") for logical_id in REQUIRED_AGENT_IDS]


@router.get("/runtimes")
async def runtimes(_: Annotated[Actor, Depends(current_actor)]):
    settings = get_settings()
    return [
        {
            "type": RuntimeType.CODEX_APP_SERVER,
            "default": True,
            "enabled": settings.codex_enabled,
            "transport": "stdio-jsonl",
        },
        {
            "type": RuntimeType.LITELLM_GATEWAY,
            "default": False,
            "enabled": settings.litellm_enabled,
            "explicit_opt_in": True,
        },
    ]


@router.get("/profiles")
async def list_profiles(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    values = await _profiles(ResourceStore(db), actor.owner_id)
    return [item.model_dump(mode="json") for item in values.values()]


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
async def save_profile(
    profile: ModelProfile,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    catalog = await _profiles(store, actor.owner_id)
    for fallback_id in profile.fallback_profile_ids:
        fallback = catalog.get(fallback_id)
        if fallback is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "fallback profile not found")
        if fallback.runtime != profile.runtime:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "cross-runtime fallback forbidden"
            )
    item = await store.create(
        "agent_profile",
        actor.owner_id,
        profile.model_dump(mode="json"),
        record_id=profile.id,
        actor_id=actor.actor_id,
        event_type="model_profile.changed",
    )
    return item.public()


@router.put("/{logical_id}")
async def configure(
    logical_id: str,
    agent: AgentDefinition,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if logical_id not in REQUIRED_AGENT_IDS or logical_id != agent.logical_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown logical agent")
    store = ResourceStore(db)
    profiles = await _profiles(store, actor.owner_id)
    if agent.profile_id:
        profile = profiles.get(agent.profile_id)
        if profile is None or profile.runtime != agent.runtime:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "runtime/profile mismatch")
    existing = next(
        (
            item
            for item in await store.list("agent_configuration", actor.owner_id)
            if item.data.get("logical_id") == logical_id
        ),
        None,
    )
    if existing:
        item = await store.update(
            existing,
            agent.model_dump(mode="json"),
            actor_id=actor.actor_id,
            event_type="agent_configuration.activated",
        )
    else:
        item = await store.create(
            "agent_configuration",
            actor.owner_id,
            agent.model_dump(mode="json"),
            actor_id=actor.actor_id,
            event_type="agent_configuration.activated",
        )
    return item.public()


@router.post("/prompt-preview")
async def preview(
    agent: PromptSet,
    orchestrator: PromptSet,
    platform: PromptSet,
    _: Annotated[Actor, Depends(current_actor)],
):
    return resolve_prompts(agent, orchestrator, platform).__dict__


@router.post("/{logical_id}/test")
async def test_run(
    logical_id: str,
    payload: AgentTestInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if logical_id not in REQUIRED_AGENT_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "logical agent not found")
    store = ResourceStore(db)
    agents = await _agents(store, actor.owner_id)
    profiles = await _profiles(store, actor.owner_id)
    agent = agents[logical_id]
    default = _default_profile()
    if agent.profile_id is None:
        agent = agent.model_copy(update={"profile_id": default.id})
    orchestrator = agents["orchestrator"]
    prompts = resolve_prompts(
        PromptSet(agent.system_prompt_override, agent.user_prompt_override),
        PromptSet(
            orchestrator.system_prompt_override,
            orchestrator.user_prompt_override,
        ),
        PromptSet(
            "You are a bounded Matrades specialist. Use only structured evidence, disclose "
            "uncertainty, and never claim broker, policy, risk, approval, or strategy authority.",
            "Analyze the supplied structured input and return concise evidence.",
        ),
    )
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "summary", "evidence", "uncertainties"],
        "additionalProperties": False,
    }
    execution, result = await runtime_router.execute(
        agent,
        profiles,
        prompts,
        PermissionSet(agent.permission_set_version, ("market.read", "knowledge.search")),
        {**payload.input, "output_schema": output_schema},
        deadline_seconds=120,
    )
    await store.create(
        "agent_execution",
        actor.owner_id,
        {
            **execution.model_dump(mode="json"),
            "result": result,
            "system_prompt_source": prompts.system_source,
            "user_prompt_source": prompts.user_source,
            "broker_authority": False,
        },
        state=execution.status,
        record_id=execution.id,
        actor_id=actor.actor_id,
        event_type="agent.test_completed",
    )
    return {"execution": execution.model_dump(mode="json"), "result": result}


@router.get("/executions")
async def list_executions(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("agent_execution", actor.owner_id)
    return [item.public() for item in records]
