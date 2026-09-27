from __future__ import annotations

import asyncio
import json
import logging
import signal
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from modules.agents.model_assignments import default_profile
from modules.agents.models import AgentDefinition, ModelProfile, RuntimeType
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import PromptSet, resolve_prompts
from modules.agents.registry import REQUIRED_AGENT_IDS
from modules.agents.rpc import AGENT_REQUEST_QUEUE
from modules.agents.runtime import AgentRuntimeRouter
from modules.credentials.vault import EnvelopeCipher
from packages.shared.config import get_settings
from packages.shared.database import unit_of_work
from packages.shared.runtime_health import (
    CODEX_APP_SERVER_HEARTBEAT_INTERVAL_SECONDS,
    CODEX_APP_SERVER_HEARTBEAT_KEY,
    CODEX_APP_SERVER_HEARTBEAT_TTL_SECONDS,
)
from packages.shared.store import ResourceStore

logger = logging.getLogger(__name__)

PLATFORM_PROMPTS = PromptSet(
    "You are a bounded Matrades logical agent. Use only supplied structured evidence, cite "
    "evidence references, state uncertainty, and never create broker, policy, risk, or "
    "strategy activation authority.",
    "Return only a JSON object conforming to the requested output schema.",
    "platform-v1",
)


def _default_profile(logical_id: str | None = None) -> ModelProfile:
    settings = get_settings()
    return default_profile(logical_id, fallback_model=settings.default_codex_model)


def codex_slots_healthy(routers: list[AgentRuntimeRouter]) -> bool:
    return any(
        bool(getattr(router.clients.get(RuntimeType.CODEX_APP_SERVER), "healthy", False))
        for router in routers
    )


async def publish_codex_heartbeat(
    routers: list[AgentRuntimeRouter], stopped: asyncio.Event
) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        while not stopped.is_set():
            try:
                if codex_slots_healthy(routers):
                    await redis.set(
                        CODEX_APP_SERVER_HEARTBEAT_KEY,
                        "healthy",
                        ex=CODEX_APP_SERVER_HEARTBEAT_TTL_SECONDS,
                    )
                else:
                    await redis.delete(CODEX_APP_SERVER_HEARTBEAT_KEY)
            except RedisError:
                logger.exception("Unable to publish the Codex App Server heartbeat")
            try:
                await asyncio.wait_for(
                    stopped.wait(),
                    timeout=CODEX_APP_SERVER_HEARTBEAT_INTERVAL_SECONDS,
                )
            except TimeoutError:
                pass
    finally:
        try:
            await redis.delete(CODEX_APP_SERVER_HEARTBEAT_KEY)
        except RedisError:
            logger.exception("Unable to clear the Codex App Server heartbeat")
        await redis.aclose()


async def serve_agent_requests(
    router: AgentRuntimeRouter,
    stopped: asyncio.Event,
) -> None:
    """Execute bounded logical-agent requests inside the isolated runtime worker."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        while not stopped.is_set():
            try:
                queued = await redis.brpop(AGENT_REQUEST_QUEUE, timeout=1)
            except RedisError:
                logger.exception("Unable to receive logical-agent requests")
                continue
            if queued is None:
                continue
            request = json.loads(queued[1])
            response_key = str(request.get("response_key", ""))
            logical_id = str(request.get("logical_id", ""))
            response: dict[str, object]
            try:
                if logical_id not in REQUIRED_AGENT_IDS:
                    raise ValueError("unknown logical agent")
                owner_id = UUID(str(request.get("owner_id") or settings.default_owner_id))
                async with unit_of_work() as db:
                    store = ResourceStore(db)
                    default = _default_profile()
                    profiles = {default.id: default}
                    for agent_id in REQUIRED_AGENT_IDS:
                        profile = _default_profile(agent_id)
                        profiles[profile.id] = profile
                    for item in await store.list("agent_profile", owner_id):
                        profile = ModelProfile.model_validate(item.data)
                        profiles[profile.id] = profile
                    agents = {
                        agent_id: AgentDefinition(logical_id=agent_id)
                        for agent_id in REQUIRED_AGENT_IDS
                    }
                    for item in await store.list("agent_configuration", owner_id):
                        configured = AgentDefinition.model_validate(item.data)
                        agents[configured.logical_id] = configured
                    agent = agents[logical_id]
                    if agent.profile_id is None:
                        agent = agent.model_copy(
                            update={"profile_id": _default_profile(logical_id).id}
                        )
                    orchestrator = agents["orchestrator"]
                    prompts = resolve_prompts(
                        PromptSet(agent.system_prompt_override, agent.user_prompt_override),
                        PromptSet(
                            orchestrator.system_prompt_override,
                            orchestrator.user_prompt_override,
                        ),
                        PLATFORM_PROMPTS,
                    )
                    execution, result = await router.execute(
                        agent,
                        profiles,
                        prompts,
                        PermissionSet(
                            agent.permission_set_version,
                            ("market.read", "knowledge.search"),
                        ),
                        {
                            **dict(request.get("payload", {})),
                            "output_schema": request.get("output_schema"),
                        },
                        # Leave time for persistence and the Redis reply before
                        # the gateway's own request deadline expires.
                        deadline_seconds=max(1, settings.research_agent_timeout_seconds - 5),
                    )
                    await store.create(
                        "agent_execution",
                        owner_id,
                        {
                            **execution.model_dump(mode="json"),
                            "result": result,
                            "system_prompt_source": prompts.system_source,
                            "user_prompt_source": prompts.user_source,
                            "owner_id": str(owner_id),
                        },
                        state=execution.status.value,
                        record_id=execution.id,
                        event_type="agent.execution_completed",
                    )
                if isinstance(result, dict):
                    response = {"result": result}
                else:
                    # Preserve the runtime/model failure instead of replacing it
                    # with the misleading gateway "invalid response" error.
                    detail = execution.error or "agent runtime returned no structured result"
                    response = {"error": f"{execution.status.value}: {detail}"}
            except Exception as exc:
                logger.exception("Logical agent %s failed", logical_id)
                response = {"error": f"{type(exc).__name__}: {exc}"}
            if response_key:
                await redis.rpush(response_key, json.dumps(response, default=str))
                await redis.expire(response_key, settings.research_agent_timeout_seconds + 30)
    finally:
        await redis.aclose()


async def start_agent_slots(
    overrides: dict[str, object], concurrency: int
) -> list[AgentRuntimeRouter]:
    """Give each Redis consumer its own runtime and Codex App Server process."""
    routers: list[AgentRuntimeRouter] = []
    try:
        for _ in range(concurrency):
            router = AgentRuntimeRouter.from_settings(overrides)
            routers.append(router)
            await router.start()
    except BaseException:
        await asyncio.gather(*(router.close() for router in routers), return_exceptions=True)
        raise
    return routers


async def serve_agent_slots(routers: list[AgentRuntimeRouter], stopped: asyncio.Event) -> None:
    await asyncio.gather(*(serve_agent_requests(router, stopped) for router in routers))


async def serve() -> None:
    overrides: dict[str, object] = {}
    try:
        async with unit_of_work() as db:
            store = ResourceStore(db)
            saved = next(
                iter(await store.list("agent_runtime_settings", get_settings().default_owner_id)),
                None,
            )
            if saved is not None:
                overrides.update(
                    {
                        key: saved.data[key]
                        for key in ("codex_enabled", "litellm_enabled", "litellm_url")
                        if key in saved.data
                    }
                )
                envelope = saved.data.get("litellm_api_key_envelope")
                if envelope:
                    overrides["litellm_api_key"] = EnvelopeCipher(
                        get_settings().secret_key.get_secret_value().encode()
                    ).decrypt(get_settings().default_owner_id, envelope)
    except Exception:  # noqa: BLE001 - retain environment defaults during first boot
        logger.exception(
            "Unable to load persisted agent runtime settings; using environment defaults"
        )
    concurrency = get_settings().agent_worker_concurrency
    routers = await start_agent_slots(overrides, concurrency)
    logger.info("Agent runtime initialized with %d independent slots", len(routers))
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    heartbeat = asyncio.create_task(publish_codex_heartbeat(routers, stopped))
    request_server = asyncio.create_task(serve_agent_slots(routers, stopped))
    try:
        await stopped.wait()
    finally:
        stopped.set()
        await asyncio.gather(heartbeat, request_server)
        await asyncio.gather(*(router.close() for router in routers))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
