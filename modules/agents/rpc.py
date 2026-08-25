"""Redis request/reply bridge to the isolated Codex App Server worker."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

AGENT_REQUEST_QUEUE = "matrades:agent:requests"
AGENT_RESPONSE_PREFIX = "matrades:agent:response:"


class RedisAgentGateway:
    def __init__(self, redis_url: str, timeout_seconds: int = 90) -> None:
        self.redis = Redis.from_url(redis_url)
        self.timeout_seconds = timeout_seconds

    async def invoke(
        self,
        logical_id: str,
        payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        response_key = f"{AGENT_RESPONSE_PREFIX}{request_id}"
        request = {
            "request_id": request_id,
            "response_key": response_key,
            "logical_id": logical_id,
            "payload": payload,
            "output_schema": output_schema,
        }
        await self.redis.lpush(AGENT_REQUEST_QUEUE, json.dumps(request, default=str))
        response = await self.redis.blpop(response_key, timeout=self.timeout_seconds)
        await self.redis.delete(response_key)
        if response is None:
            raise TimeoutError(f"{logical_id} did not respond before the deadline")
        body = json.loads(response[1])
        if body.get("error"):
            raise RuntimeError(str(body["error"]))
        result = body.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"{logical_id} returned an invalid response")
        return result

    async def close(self) -> None:
        await self.redis.aclose()
