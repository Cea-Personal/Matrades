"""Single-agent UI endpoints must enqueue and execute only their selected role."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.agent_worker.app import main as worker
from apps.api.app.routes import agents as api_agents
from modules.agents.models import AgentExecution, ExecutionStatus
from modules.agents.registry import REQUIRED_AGENT_IDS
from modules.agents.rpc import AGENT_REQUEST_QUEUE
from modules.identity.authorization import Actor, Role


@pytest.mark.parametrize("logical_id", REQUIRED_AGENT_IDS)
async def test_one_http_test_request_enqueues_and_executes_only_selected_agent(
    monkeypatch, logical_id
):
    actor = Actor(uuid4(), uuid4(), Role.OWNER, False)
    stopped = asyncio.Event()
    executed = []
    enqueued = []
    persisted = []

    class Store:
        def __init__(self, db):
            pass

        async def list(self, kind, owner_id):
            assert owner_id == actor.owner_id
            return []

        async def create(self, kind, owner_id, data, **kwargs):
            assert kind == "agent_execution" and owner_id == actor.owner_id
            persisted.append(data)

    class Router:
        async def execute(self, agent, profiles, prompts, permissions, payload, **kwargs):
            executed.append(agent.logical_id)
            assert permissions.tools == ()  # Domain evidence is supplied, not registered tools.
            assert payload["purpose"] == "configuration_test"
            profile = profiles[agent.profile_id]
            stopped.set()
            execution = AgentExecution(
                logical_id=agent.logical_id,
                selected_runtime=agent.runtime,
                actual_runtime=agent.runtime,
                configured_model=profile.model,
                requested_model=profile.model,
                resolved_system_prompt=prompts.system,
                resolved_user_prompt=prompts.user,
                tools=permissions.tools,
                status=ExecutionStatus.SUCCEEDED,
                duration_ms=1,
            )
            return execution, {"status": "OK", "summary": "Selected agent only"}

    class Redis:
        def __init__(self):
            self.requests = []
            self.responses = {}

        async def lpush(self, key, body):
            assert key == AGENT_REQUEST_QUEUE
            request = json.loads(body)
            enqueued.append(request)
            self.requests.append(body)

        async def brpop(self, key, **kwargs):
            assert key == AGENT_REQUEST_QUEUE
            return key, self.requests.pop()

        async def blpop(self, key, **kwargs):
            # Run the real worker consumer against the request the real API
            # gateway just queued. No model calls, database writes or live Redis.
            await worker.serve_agent_requests(Router(), stopped)
            return key, self.responses[key]

        async def rpush(self, key, body):
            self.responses[key] = body

        async def expire(self, key, seconds):
            pass

        async def delete(self, key):
            self.responses.pop(key)

        async def aclose(self):
            pass

    @asynccontextmanager
    async def unit_of_work():
        yield None

    async def database():
        yield None

    redis = Redis()
    monkeypatch.setattr(worker.Redis, "from_url", lambda url: redis)
    monkeypatch.setattr(worker, "unit_of_work", unit_of_work)
    monkeypatch.setattr(worker, "ResourceStore", Store)
    monkeypatch.setattr(api_agents, "ResourceStore", Store)
    app = FastAPI()
    app.include_router(api_agents.router, prefix="/api/v1")
    app.dependency_overrides[api_agents.current_actor] = lambda: actor
    app.dependency_overrides[api_agents.get_db] = database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/agents/{logical_id}/test",
            json={"input": {"purpose": "configuration_test"}},
        )
    assert response.status_code == 200
    assert response.json()["execution"]["logical_id"] == logical_id
    assert [request["logical_id"] for request in enqueued] == [logical_id]
    assert enqueued[0]["owner_id"] == str(actor.owner_id)
    assert executed == [logical_id]
    assert [record["logical_id"] for record in persisted] == [logical_id]
    assert not redis.requests


async def test_unknown_agent_does_not_enqueue_any_test(monkeypatch):
    gateway = AsyncMock()
    monkeypatch.setattr(api_agents, "RedisAgentGateway", gateway)
    app = FastAPI()
    app.include_router(api_agents.router, prefix="/api/v1")
    actor = Actor(uuid4(), uuid4(), Role.OWNER, False)
    app.dependency_overrides[api_agents.current_actor] = lambda: actor
    app.dependency_overrides[api_agents.get_db] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/agents/not-an-agent/test", json={})
    assert response.status_code == 404
    gateway.assert_not_called()
