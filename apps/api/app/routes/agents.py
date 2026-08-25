from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Annotated, Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.agents.models import (
    AgentDefinition,
    AgentExecution,
    ExecutionStatus,
    ModelProfile,
    RuntimeType,
)
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import PromptSet, resolve_prompts
from modules.agents.registry import REQUIRED_AGENT_IDS
from modules.agents.rpc import RedisAgentGateway
from modules.agents.runtime import AgentRuntimeRouter
from modules.connections.models import validated_endpoint
from modules.credentials.vault import EnvelopeCipher
from modules.identity.authorization import Actor, Role
from packages.shared.config import get_settings
from packages.shared.runtime_health import CODEX_APP_SERVER_HEARTBEAT_KEY
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/agents", tags=["Agents"])
runtime_router = AgentRuntimeRouter.from_settings()


class AgentTestInput(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class RuntimeSettingsInput(BaseModel):
    codex_enabled: bool = True
    litellm_enabled: bool = False
    litellm_url: str = Field(default="http://localhost:4000", min_length=1)
    litellm_api_key: str | None = None
    default_codex_model: str = Field(default="gpt-5.6-terra", min_length=1)


def _runtime_cipher() -> EnvelopeCipher:
    return EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())


async def _saved_runtime_settings(store: ResourceStore, owner_id: UUID) -> dict[str, Any]:
    settings = get_settings()
    record = next(iter(await store.list("agent_runtime_settings", owner_id)), None)
    if record is None:
        return {
            "codex_enabled": settings.codex_enabled,
            "litellm_enabled": settings.litellm_enabled,
            "litellm_url": settings.litellm_url,
            "default_codex_model": settings.default_codex_model,
            "litellm_api_key_configured": bool(settings.litellm_api_key),
            "updated_at": None,
        }
    return {
        "codex_enabled": record.data.get("codex_enabled", settings.codex_enabled),
        "litellm_enabled": record.data.get("litellm_enabled", settings.litellm_enabled),
        "litellm_url": record.data.get("litellm_url", settings.litellm_url),
        "default_codex_model": record.data.get("default_codex_model", settings.default_codex_model),
        "litellm_api_key_configured": bool(record.data.get("litellm_api_key_envelope")),
        "updated_at": record.updated_at,
    }


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
        logical_id: AgentDefinition(logical_id=logical_id) for logical_id in REQUIRED_AGENT_IDS
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
async def runtimes(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    saved = await _saved_runtime_settings(ResourceStore(db), actor.owner_id)
    return [
        {
            "type": RuntimeType.CODEX_APP_SERVER,
            "default": True,
            "enabled": saved["codex_enabled"],
            "transport": "stdio-jsonl",
        },
        {
            "type": RuntimeType.LITELLM_GATEWAY,
            "default": False,
            "enabled": saved["litellm_enabled"],
            "explicit_opt_in": True,
            "url": saved["litellm_url"],
            "api_key_configured": saved["litellm_api_key_configured"],
        },
    ]


@router.get("/runtime-settings")
async def runtime_settings(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return {
        **(await _saved_runtime_settings(ResourceStore(db), actor.owner_id)),
        "restart_required": True,
    }


@router.put("/runtime-settings")
async def save_runtime_settings(
    payload: RuntimeSettingsInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        url = validated_endpoint(payload.litellm_url, allow_loopback_http=True)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    store = ResourceStore(db)
    existing = next(iter(await store.list("agent_runtime_settings", actor.owner_id)), None)
    data: dict[str, Any] = {
        "codex_enabled": payload.codex_enabled,
        "litellm_enabled": payload.litellm_enabled,
        "litellm_url": url,
        "default_codex_model": payload.default_codex_model,
    }
    if payload.litellm_api_key:
        data["litellm_api_key_envelope"] = (
            _runtime_cipher().encrypt(actor.owner_id, payload.litellm_api_key).as_dict()
        )
        data["litellm_api_key_suffix"] = payload.litellm_api_key[-4:]
    elif existing is not None and existing.data.get("litellm_api_key_envelope"):
        data["litellm_api_key_envelope"] = existing.data["litellm_api_key_envelope"]
        data["litellm_api_key_suffix"] = existing.data.get("litellm_api_key_suffix")
    if existing is None:
        item = await store.create(
            "agent_runtime_settings",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="agent_runtime_settings.changed",
        )
    else:
        item = await store.update(
            existing, data, actor_id=actor.actor_id, event_type="agent_runtime_settings.changed"
        )
    return {
        **(await _saved_runtime_settings(store, actor.owner_id)),
        "restart_required": True,
        "saved_at": item.updated_at,
    }


@router.post("/runtime-settings/test")
async def test_runtime_settings(
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    config = await _saved_runtime_settings(ResourceStore(db), actor.owner_id)
    if not config["litellm_enabled"]:
        return {"status": "DISABLED", "message": "LiteLLM gateway is disabled"}
    url = str(config["litellm_url"]).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{url}/health")
        response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "OFFLINE", "message": f"LiteLLM gateway unavailable: {exc}"}
    return {
        "status": "HEALTHY",
        "message": "LiteLLM gateway responded",
        "checked_at": datetime.now(UTC),
    }


@router.get("/status")
async def agent_status(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    agents = await _agents(store, actor.owner_id)
    executions = await store.list("agent_execution", actor.owner_id)
    latest: dict[str, Any] = {}
    for record in executions:
        logical_id = str(record.data.get("logical_id"))
        if logical_id not in latest:
            latest[logical_id] = record
    heartbeat = False
    redis = Redis.from_url(get_settings().redis_url)
    try:
        heartbeat = bool(await redis.get(CODEX_APP_SERVER_HEARTBEAT_KEY))
    except (RedisError, OSError):
        heartbeat = False
    finally:
        await redis.aclose()
    rows = []
    for logical_id in REQUIRED_AGENT_IDS:
        configured = agents[logical_id]
        execution = latest.get(logical_id)
        data = execution.data if execution else {}
        rows.append(
            {
                "logical_id": logical_id,
                "configured_runtime": configured.runtime,
                "actual_runtime": data.get("actual_runtime"),
                "last_status": data.get("status"),
                "last_error": data.get("error"),
                "last_tested_at": execution.updated_at if execution else None,
                "evidence": "agent_execution" if execution else "not_tested",
            }
        )
    return {
        "codex_worker_heartbeat": heartbeat,
        "runtime_settings": await _saved_runtime_settings(store, actor.owner_id),
        "agents": rows,
    }


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
    profile_id = agent.profile_id or default.id
    if agent.profile_id is None:
        agent = agent.model_copy(update={"profile_id": default.id})
    profile = profiles[profile_id]
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
    configured_profile = agent.profile_id is not None
    if agent.runtime == RuntimeType.CODEX_APP_SERVER:
        started = monotonic()
        result: dict[str, Any] | None = None
        error: str | None = None
        gateway = RedisAgentGateway(
            get_settings().redis_url,
            get_settings().research_agent_timeout_seconds,
        )
        try:
            result = await gateway.invoke(
                logical_id,
                {**payload.input, "purpose": "configuration_test"},
                output_schema,
            )
            execution_status = ExecutionStatus.SUCCEEDED
        except (TimeoutError, RuntimeError, ValueError) as exc:
            execution_status = ExecutionStatus.DEGRADED
            error = str(exc)
        finally:
            await gateway.close()
        execution = AgentExecution(
            logical_id=agent.logical_id,
            selected_runtime=agent.runtime,
            actual_runtime=agent.runtime,
            selection_source="agent_profile" if configured_profile else "codex_default",
            configured_model=profile.model,
            actual_model=profile.model,
            resolved_system_prompt=prompts.system,
            resolved_user_prompt=prompts.user,
            tools=("market.read", "knowledge.search"),
            status=execution_status,
            duration_ms=int((monotonic() - started) * 1000),
            error=error,
        )
    else:
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
