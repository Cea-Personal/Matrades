import asyncio
import json
import tomllib
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from adapters.agent_runtime.codex_app_server.client import CodexAppServerClient
from adapters.agent_runtime.litellm.client import LiteLLMClient
from adapters.agent_runtime.result import RuntimeResult
from apps.api.app.routes import agents as api_agents
from modules.agents.model_assignments import default_profile
from modules.agents.models import AgentDefinition, AgentExecution, RuntimeType
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import ResolvedPrompts
from modules.agents.rpc import RedisAgentGateway
from modules.agents.runtime import AgentRuntimeRouter


@pytest.mark.parametrize("model", ['custom-"model', r"custom-\1-model"])
def test_role_snapshot_preserves_native_contract_and_permissions(tmp_path, model):
    client = CodexAppServerClient()
    source = client.native_agents_dir / "critic.toml"
    original = source.read_text()
    native = tomllib.loads(original)
    snapshot = client._snapshot_role("critic", native, model, "high", tmp_path)
    assert tomllib.loads(snapshot.read_text()) == {
        **native,
        "model": model,
        "model_reasoning_effort": "high",
    }
    assert source.read_text() == original


def test_rollout_model_comes_from_turn_context_not_requested_spawn_or_output(tmp_path):
    path = tmp_path / "rollout-test-child.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(item)
            for item in [
                {"type": "session_meta", "payload": {"model": "requested-model"}},
                {"type": "turn_context", "payload": {"model": "runtime-model"}},
                {"type": "response_item", "payload": {"model": "agent-claimed-model"}},
            ]
        )
    )
    assert CodexAppServerClient._rollout_model(str(path), "child") == "runtime-model"
    assert CodexAppServerClient._rollout_model(str(path), "different-thread") is None
    assert CodexAppServerClient._rollout_model(None, "child") is None


@pytest.mark.parametrize("own_turn", [True, False])
async def test_child_model_evidence_is_kept_outside_strategy_json(tmp_path, monkeypatch, own_turn):
    path = tmp_path / "rollout-test-child.jsonl"
    await asyncio.to_thread(
        path.write_text,
        json.dumps(
            {
                "type": "turn_context",
                "payload": {
                    "model": "observed-child-model",
                    "turn_id": "child-turn" if own_turn else "turn",
                },
            }
        ),
    )
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)
    events = iter(
        [
            {
                "method": "item/completed",
                "params": {
                    "threadId": "parent",
                    "item": {
                        "type": "collabAgentToolCall",
                        "tool": "spawnAgent",
                        "status": "completed",
                        "receiverThreadIds": ["child"],
                        "model": "requested-not-actual",
                    },
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"ok":true}',
                    }
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "id": "turn",
                        "status": "completed",
                    }
                },
            },
        ]
    )

    async def request(method, params):
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        assert method == "thread/read" and params["threadId"] == "child"
        return {"thread": {"id": "child", "agentRole": "critic", "path": str(path)}}

    async def read_message(**kwargs):
        return next(events)

    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(client, "_read_message", read_message)
    result = await client._invoke_thread({}, "critic", "parent")
    assert result == {"ok": True}
    assert json.dumps(result) == '{"ok": true}'
    assert result.actual_model == ("observed-child-model" if own_turn else None)
    assert result.model_evidence_source == ("codex_turn_context" if own_turn else None)


@pytest.mark.parametrize("verified", [True, False])
async def test_runtime_distinguishes_requested_and_observed_model(verified):
    profile = default_profile("critic")
    agent = AgentDefinition(logical_id="critic", profile_id=profile.id)

    class Client:
        async def invoke(self, payload):
            assert payload["model"] == profile.model
            assert payload["reasoning_effort"] == profile.parameters["reasoning_effort"]
            if verified:
                return RuntimeResult(
                    {"ok": True},
                    actual_model="resolved-model",
                    model_evidence_source="codex_turn_context",
                )
            return {"ok": True, "actual_model": "untrusted-agent-claim"}

    execution, result = await AgentRuntimeRouter({RuntimeType.CODEX_APP_SERVER: Client()}).execute(
        agent,
        {profile.id: profile},
        ResolvedPrompts("s", "u", "platform", "platform"),
        PermissionSet("v1", ("market.read",)),
        {},
    )
    assert result["ok"]
    assert execution.requested_model == profile.model
    assert execution.selection_source == "native_agent"
    assert execution.actual_model == ("resolved-model" if verified else None)
    assert execution.model_verified is verified


@pytest.mark.parametrize("model", ["provider-resolved-model", None])
async def test_gateway_model_evidence_uses_response_metadata(model):
    def respond(request):
        return httpx.Response(
            200, json={"model": model, "choices": [{"message": {"content": '{"ok":true}'}}]}
        )

    http = httpx.AsyncClient(base_url="http://gateway", transport=httpx.MockTransport(respond))
    client = LiteLLMClient("http://gateway", "test-credential", client=http)
    try:
        result = await client.invoke({"model": "requested-alias"})
        assert result == {"ok": True}
        assert result.actual_model == model
        assert result.model_evidence_source == ("gateway_response" if model else None)
    finally:
        await client.close()


async def test_registry_displays_native_default_and_preserves_saved_override(monkeypatch):
    saved = default_profile("critic").model_copy(
        update={
            "id": uuid4(),
            "model": "saved-custom-model",
            "parameters": {"reasoning_effort": "high"},
        }
    )

    class Store:
        def __init__(self, db):
            pass

        async def list(self, kind, owner_id):
            if kind == "agent_profile":
                return [SimpleNamespace(data=saved.model_dump(mode="json"))]
            if kind == "agent_configuration":
                return [
                    SimpleNamespace(
                        data=AgentDefinition(logical_id="critic", profile_id=saved.id).model_dump(
                            mode="json"
                        )
                    )
                ]
            return []

    monkeypatch.setattr(api_agents, "ResourceStore", Store)
    rows = await api_agents.list_agents(SimpleNamespace(owner_id=uuid4()), None)
    critic = next(row for row in rows if row["logical_id"] == "critic")
    assert critic["configured_model"] == "saved-custom-model"
    assert critic["configured_reasoning_effort"] == "high"
    assert critic["recommended_model"] == default_profile("critic").model
    assert critic["model_source"] == "profile_override"
    native = next(row for row in rows if row["logical_id"] == "technical_analyst")
    assert native["configured_model"] == default_profile("technical_analyst").model
    assert native["model_source"] == "native_agent"


@pytest.mark.parametrize("status", ["SUCCEEDED", "DEGRADED"])
async def test_api_test_reuses_worker_execution_instead_of_fabricating_second_record(
    monkeypatch, status
):
    profile = default_profile("critic")
    execution = AgentExecution(
        logical_id="critic",
        selected_runtime=RuntimeType.CODEX_APP_SERVER,
        actual_runtime=RuntimeType.CODEX_APP_SERVER,
        selection_source="native_agent",
        configured_model=profile.model,
        requested_model=profile.model,
        actual_model="worker-verified-model",
        model_verified=True,
        model_evidence_source="codex_turn_context",
        resolved_system_prompt="s",
        resolved_user_prompt="u",
        tools=(),
        status=status,
        duration_ms=1,
    )

    class Store:
        def __init__(self, db):
            pass

        async def list(self, kind, owner_id):
            return []

        async def create(self, *args, **kwargs):
            raise AssertionError("Worker execution must not be duplicated")

    class Gateway:
        def __init__(self, *args):
            pass

        async def invoke(self, *args, **kwargs):
            assert kwargs["include_execution"] is True
            return {"result": {"ok": True}, "execution": execution.model_dump(mode="json")}

        async def close(self):
            pass

    monkeypatch.setattr(api_agents, "ResourceStore", Store)
    monkeypatch.setattr(api_agents, "RedisAgentGateway", Gateway)
    result = await api_agents.test_run(
        "critic", api_agents.AgentTestInput(), SimpleNamespace(owner_id=uuid4()), None
    )
    assert result["execution"]["id"] == str(execution.id)
    assert result["execution"]["actual_model"] == "worker-verified-model"


async def test_status_does_not_present_legacy_requested_models_as_verified(monkeypatch):
    class Store:
        def __init__(self, db):
            pass

        async def list(self, kind, owner_id):
            if kind == "agent_execution":
                return [
                    SimpleNamespace(
                        id=uuid4(),
                        updated_at="2026-09-27T10:00:00Z",
                        data={
                            "logical_id": "critic",
                            "actual_model": "old-requested-model",
                            "configured_model": "old-requested-model",
                            "status": "SUCCEEDED",
                        },
                    )
                ]
            return []

    class Redis:
        async def get(self, key):
            return True

        async def aclose(self):
            pass

    async def runtime_settings(*args):
        return {}

    monkeypatch.setattr(api_agents, "ResourceStore", Store)
    monkeypatch.setattr(api_agents.Redis, "from_url", lambda url: Redis())
    monkeypatch.setattr(api_agents, "_saved_runtime_settings", runtime_settings)
    status = await api_agents.agent_status(SimpleNamespace(owner_id=uuid4()), None)
    critic = next(row for row in status["agents"] if row["logical_id"] == "critic")
    assert critic["actual_model"] is None
    assert critic["model_verified"] is False
    assert critic["requested_model"] == "old-requested-model"


async def test_rpc_execution_envelope_does_not_pollute_agent_results(monkeypatch):
    class Redis:
        async def lpush(self, key, body):
            pass

        async def blpop(self, key, **kwargs):
            return key, json.dumps({"result": {"ok": True}, "execution": {"id": "proof"}})

        async def delete(self, key):
            pass

    monkeypatch.setattr("modules.agents.rpc.Redis.from_url", lambda url: Redis())
    gateway = RedisAgentGateway("redis://test")
    assert await gateway.invoke("critic", {}, {}) == {"ok": True}
    envelope = await gateway.invoke("critic", {}, {}, include_execution=True)
    assert envelope["execution"] == {"id": "proof"}
