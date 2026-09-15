import asyncio
import json
from types import SimpleNamespace

from adapters.agent_runtime.codex_app_server.client import (
    CODEX_APP_SERVER_JSONL_LIMIT,
    CodexAppServerClient,
)


async def test_codex_jsonl_reader_accepts_frames_above_asyncio_default_limit() -> None:
    reader = asyncio.StreamReader(limit=CODEX_APP_SERVER_JSONL_LIMIT)
    message = {"method": "item/completed", "params": {"text": "x" * 100_000}}
    reader.feed_data((json.dumps(message) + "\n").encode())
    client = CodexAppServerClient()
    client.process = SimpleNamespace(stdout=reader, stderr=None, returncode=None)

    assert await client._read_message(
        read_timeout_seconds=1, closed_message="closed"
    ) == message


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
