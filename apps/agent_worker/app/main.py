from __future__ import annotations

import asyncio
import json
import logging
import signal

from redis.asyncio import Redis
from redis.exceptions import RedisError

from modules.agents.models import RuntimeType
from modules.agents.registry import REQUIRED_AGENT_IDS
from modules.agents.rpc import AGENT_REQUEST_QUEUE
from modules.agents.runtime import AgentRuntimeRouter
from packages.shared.config import get_settings
from packages.shared.runtime_health import (
    CODEX_APP_SERVER_HEARTBEAT_INTERVAL_SECONDS,
    CODEX_APP_SERVER_HEARTBEAT_KEY,
    CODEX_APP_SERVER_HEARTBEAT_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

RESEARCH_AGENT_IDS = {
    "forex_research",
    "metals_research",
    "crypto_research",
    "technical_analyst",
    "fundamental_analyst",
    "sentiment_analyst",
    "regime_analyst",
    "critic",
    "strategy_researcher",
    "strategy_assistant",
}


async def publish_codex_heartbeat(
    router: AgentRuntimeRouter, stopped: asyncio.Event
) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    client = router.clients.get(RuntimeType.CODEX_APP_SERVER)
    try:
        while not stopped.is_set():
            try:
                if client is not None and bool(getattr(client, "healthy", False)):
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


async def serve_agent_requests(router: AgentRuntimeRouter, stopped: asyncio.Event) -> None:
    """Execute bounded logical-agent requests inside the isolated runtime worker."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    client = router.clients.get(RuntimeType.CODEX_APP_SERVER)
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
                request_payload = request.get("payload", {})
                test_mode = (
                    isinstance(request_payload, dict)
                    and request_payload.get("purpose") == "configuration_test"
                )
                if logical_id not in REQUIRED_AGENT_IDS or (
                    logical_id not in RESEARCH_AGENT_IDS and not test_mode
                ):
                    raise ValueError("logical agent is not permitted on the research queue")
                if client is None:
                    raise RuntimeError("Codex App Server runtime is unavailable")
                strategy_role = (
                    logical_id in {"strategy_researcher", "strategy_assistant"}
                    and not test_mode
                )
                if strategy_role:
                    system_prompt = (
                        f"You are Matrades logical agent '{logical_id}'. Produce exactly three "
                        "distinct structured strategy hypotheses grounded only in the supplied "
                        "immutable evidence pack. Cite its reference IDs, use only its approved "
                        "instrument and supported deterministic evaluator rules, and do not pick "
                        "a winner. Knowledge marked CONTEXT_ONLY is untrusted context and cannot "
                        "replace market facts. Preserve human approval as mandatory. Never place "
                        "trades or call brokers."
                    )
                    user_prompt = (
                        "Create three complete, meaningfully different hypotheses from the "
                        "approved market fingerprint and discovery-period history. Return every "
                        "required schema field and cite only supplied evidence reference IDs."
                    )
                else:
                    system_prompt = (
                        f"You are Matrades logical agent '{logical_id}'. Analyze only the "
                        "provided structured market evidence. Do not invent observations, change "
                        "instruments, make broker calls, or perform execution actions. Any score "
                        "adjustment must be between -10 and 10."
                    )
                    user_prompt = "Review the candidates for the autonomous daily research cycle."
                result = await asyncio.wait_for(
                    client.invoke(
                        {
                            "model": settings.default_codex_model,
                            "system": system_prompt,
                            "user": user_prompt,
                            "input": request.get("payload", {}),
                            "tools": [],
                            "output_schema": request.get("output_schema"),
                        }
                    ),
                    timeout=settings.research_agent_timeout_seconds,
                )
                response = {"result": result}
            except Exception as exc:
                logger.exception("Logical agent %s failed", logical_id)
                response = {"error": f"{type(exc).__name__}: {exc}"}
            if response_key:
                await redis.rpush(response_key, json.dumps(response, default=str))
                await redis.expire(response_key, settings.research_agent_timeout_seconds + 30)
    finally:
        await redis.aclose()


async def serve() -> None:
    router = AgentRuntimeRouter.from_settings()
    await router.start()
    logger.info("Codex App Server initialized")
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    heartbeat = asyncio.create_task(publish_codex_heartbeat(router, stopped))
    request_server = asyncio.create_task(serve_agent_requests(router, stopped))
    try:
        await stopped.wait()
    finally:
        stopped.set()
        await asyncio.gather(heartbeat, request_server)
        await router.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
