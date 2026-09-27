import asyncio
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace

from adapters.agent_runtime.codex_app_server.client import (
    CODEX_APP_SERVER_JSONL_LIMIT,
    CodexAppServerClient,
)
from modules.agents.native_config import load_native_agent


async def test_codex_jsonl_reader_accepts_frames_above_asyncio_default_limit() -> None:
    reader = asyncio.StreamReader(limit=CODEX_APP_SERVER_JSONL_LIMIT)
    message = {"method": "item/completed", "params": {"text": "x" * 100_000}}
    reader.feed_data((json.dumps(message) + "\n").encode())
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=reader, stderr=None, returncode=None)

    assert await client._read_message(read_timeout_seconds=1, closed_message="closed") == message


async def test_malformed_jsonl_resets_process_before_next_lane() -> None:
    reader = asyncio.StreamReader(limit=CODEX_APP_SERVER_JSONL_LIMIT)
    reader.feed_data(b"{not-json}\n")
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=reader, stderr=None, returncode=0)

    try:
        await client._read_message(read_timeout_seconds=1, closed_message="closed")
    except ValueError as exc:
        assert str(exc) == "Codex app-server emitted malformed JSONL"
    else:
        raise AssertionError("malformed JSONL must fail")
    assert client.process is None


async def test_rpc_preserves_notifications_arriving_before_its_reply(monkeypatch) -> None:
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)
    event = {"method": "item/completed", "params": {"item": {"type": "agentMessage"}}}
    messages = iter([event, {"id": 1, "result": {"turn": {"id": "turn"}}}])

    async def write(message):
        pass

    async def read_message(**kwargs):
        return next(messages)

    monkeypatch.setattr(client, "_write", write)
    monkeypatch.setattr(client, "_read_message", read_message)
    assert await client._request("turn/start", {}) == {"turn": {"id": "turn"}}
    assert client._pending_notifications.popleft() == event


async def test_invoke_uses_only_parent_final_answer_after_subagent_messages() -> None:
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)

    async def start() -> None:
        return None

    async def request(method: str, params: dict) -> dict:
        if method == "thread/start":
            assert params["ephemeral"] is False
            assert params["model"] == load_native_agent("orchestrator")["model"]
            assert params["config"]["model_reasoning_effort"] == "medium"
            snapshot = Path(params["config"]["agents.technical_analyst.config_file"])
            assert (
                await asyncio.to_thread(lambda: tomllib.loads(snapshot.read_text())["model"])
                == "explicit-specialist"
            )
            assert 'agent_type="technical_analyst"' in params["developerInstructions"]
            assert "fork_context=true" in params["developerInstructions"]
            return {"thread": {"id": "parent-thread"}}
        if method == "turn/start":
            assert params["model"] == load_native_agent("orchestrator")["model"]
            assert params["effort"] == "medium"
            assert "NATIVE SUBAGENT DELEGATION" not in params["input"][0]["text"]
            assert 'OUTPUT SCHEMA:\n{"type": "object"}' in params["input"][0]["text"]
            return {"turn": {"id": "parent-turn"}}
        assert method == "thread/delete" and params == {"threadId": "parent-thread"}
        return {}

    events = iter(
        [
            {
                "method": "item/completed",
                "params": {
                    "threadId": "parent-thread",
                    "turnId": "parent-turn",
                    "item": {
                        "type": "collabAgentToolCall",
                        "tool": "spawnAgent",
                        "status": "completed",
                    },
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "parent-thread",
                    "turnId": "parent-turn",
                    "item": {"type": "agentMessage", "phase": "commentary", "text": "Delegating"},
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "child-thread",
                    "turnId": "child-turn",
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"decision":"wrong thread"}',
                    },
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "parent-thread",
                    "turnId": "parent-turn",
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"decision":"PASS"}',
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "parent-turn", "status": "completed"}},
            },
        ]
    )

    async def read_message(**kwargs: object) -> dict:
        return next(events)

    client.start = start
    client._request = request
    client._read_message = read_message
    assert await client.invoke(
        {
            "agent_role": "technical_analyst",
            "model": "explicit-specialist",
            "output_schema": {"type": "object"},
        }
    ) == {"decision": "PASS"}


async def test_invoke_uses_last_completed_message_when_phase_is_unavailable() -> None:
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)

    async def start() -> None:
        return None

    async def request(method: str, params: dict) -> dict:
        if method == "thread/start":
            return {"thread": {"id": "thread"}}
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        assert method == "thread/delete"
        return {}

    events = iter(
        [
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": "Working"}},
            },
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": '{"decision":"PASS"}'}},
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn", "status": "completed"}}},
        ]
    )

    async def read_message(**kwargs: object) -> dict:
        return next(events)

    client.start = start
    client._request = request
    client._read_message = read_message
    assert await client.invoke({"agent_role": "orchestrator"}) == {"decision": "PASS"}


async def test_specialist_fails_closed_when_native_delegation_did_not_run() -> None:
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)

    async def start() -> None:
        return None

    async def request(method: str, params: dict) -> dict:
        if method == "thread/start":
            return {"thread": {"id": "thread"}}
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        assert method == "thread/delete"
        return {}

    events = iter(
        [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"decision":"REASSESS","score_adjustments":[],"evidence":[]}',
                    }
                },
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn", "status": "completed"}}},
        ]
    )

    async def read_message(**kwargs: object) -> dict:
        return next(events)

    client.start = start
    client._request = request
    client._read_message = read_message
    try:
        await client.invoke({"agent_role": "technical_analyst"})
    except RuntimeError as exc:
        assert "did not complete native spawn_agent delegation" in str(exc)
    else:
        raise AssertionError("specialist must not accept a parent-only answer")


async def test_invalid_json_still_deletes_parent_thread() -> None:
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=object(), returncode=None)
    deleted: list[str] = []

    async def start() -> None:
        return None

    async def request(method: str, params: dict) -> dict:
        if method == "thread/start":
            return {"thread": {"id": "thread"}}
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        assert method == "thread/delete"
        deleted.append(params["threadId"])
        return {}

    events = iter(
        [
            {
                "method": "item/completed",
                "params": {
                    "item": {"type": "agentMessage", "phase": "final_answer", "text": "invalid"}
                },
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn", "status": "completed"}}},
        ]
    )

    async def read_message(**kwargs: object) -> dict:
        return next(events)

    client.start = start
    client._request = request
    client._read_message = read_message
    try:
        await client.invoke({"agent_role": "orchestrator"})
    except ValueError as exc:
        assert str(exc) == "Codex response was not valid structured JSON"
    else:
        raise AssertionError("invalid JSON must fail")
    assert deleted == ["thread"]
