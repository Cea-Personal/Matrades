from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

CODEX_APP_SERVER_JSONL_LIMIT = 8 * 1024 * 1024


class CodexAppServerClient:
    """Supervises the official JSONL stdio app-server protocol."""

    runtime_type = "CODEX_APP_SERVER"

    def __init__(self, binary: str = "codex", cwd: Path | None = None) -> None:
        self.binary = binary
        self.cwd = cwd or Path.cwd()
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    @property
    def healthy(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        if self.healthy:
            return
        self.process = await asyncio.create_subprocess_exec(
            self.binary,
            "app-server",
            "--listen",
            "stdio://",
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # App-server JSONL events may echo the complete structured research
            # input. asyncio's 64 KiB default corrupts the stream on those frames.
            limit=CODEX_APP_SERVER_JSONL_LIMIT,
        )
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "matrades",
                    "title": "Matrades Agent Runtime",
                    "version": "0.1.0",
                }
            },
        )
        await self._notify("initialized", {})

    async def stop(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            await self.start()
            model = str(payload.get("model", ""))
            thread = await self._request(
                "thread/start",
                {
                    "model": model,
                    "cwd": str(self.cwd),
                    "approvalPolicy": "never",
                    # Codex App Server uses kebab-case sandbox policy values.
                    # Keep this read-only: research agents must not write files
                    # or perform broker/execution actions.
                    "sandbox": "read-only",
                    "serviceName": "matrades",
                    "ephemeral": True,
                },
            )
            thread_id = thread["thread"]["id"]
            prompt = (
                f"SYSTEM CONTRACT:\n{payload.get('system', '')}\n\n"
                f"USER CONTRACT:\n{payload.get('user', '')}\n\n"
                "Return only one JSON object matching the requested output schema. "
                "Do not run commands, modify files, access credentials, or perform "
                "broker actions.\n\n"
                f"STRUCTURED INPUT:\n{json.dumps(payload.get('input', payload), default=str)}"
            )
            params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(self.cwd),
                "approvalPolicy": "never",
                # `turn/start` uses the app-server policy enum spelling, which
                # differs from the `thread/start` sandbox string above.
                "sandboxPolicy": {"type": "readOnly", "access": {"type": "fullAccess"}},
                "model": model,
            }
            if payload.get("output_schema"):
                params["outputSchema"] = payload["output_schema"]
            turn = await self._request("turn/start", params)
            turn_id = turn["turn"]["id"]
            deltas: list[str] = []
            completed_messages: list[str] = []
            assert self.process is not None and self.process.stdout is not None
            while True:
                message = await self._read_message(
                    read_timeout_seconds=120,
                    closed_message="Codex app-server exited before turn completion",
                    include_stderr=True,
                )
                method = message.get("method")
                params_value = message.get("params", {})
                if method == "item/completed":
                    item = params_value.get("item", {})
                    if item.get("type") == "agentMessage" and item.get("text"):
                        completed_messages.append(str(item["text"]))
                elif method == "item/agentMessage/delta":
                    delta = params_value.get("delta")
                    if delta:
                        deltas.append(str(delta))
                elif method == "turn/completed":
                    completed = params_value.get("turn", {})
                    if completed.get("id") != turn_id:
                        continue
                    if completed.get("status") not in {"completed", "succeeded"}:
                        error = completed.get("error") or completed.get("status")
                        raise RuntimeError(str(error))
                    break
                elif method == "error":
                    raise RuntimeError(str(params_value.get("error", params_value)))
            # Current app-server releases emit both streaming deltas and the final
            # completed item. Prefer the authoritative completed item so the JSON
            # payload is not accidentally concatenated twice.
            text = "".join(completed_messages or deltas).strip()
            try:
                result = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("Codex response was not valid structured JSON") from exc
            if not isinstance(result, dict):
                raise ValueError("Codex response must be a JSON object")
            return result

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        await self._write({"method": method, "id": request_id, "params": params})
        assert self.process is not None and self.process.stdout is not None
        while True:
            message = await self._read_message(
                read_timeout_seconds=30,
                closed_message="Codex app-server closed its stdout",
            )
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return dict(message.get("result", {}))

    async def _read_message(
        self,
        *,
        read_timeout_seconds: float,
        closed_message: str,
        include_stderr: bool = False,
    ) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        try:
            raw = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=read_timeout_seconds
            )
        except (asyncio.LimitOverrunError, ValueError) as exc:
            # readline() leaves an over-limit JSONL frame in the buffer. Restart
            # the app-server so the next lane cannot consume a poisoned stream.
            await self.stop()
            raise RuntimeError(
                f"Codex app-server JSONL frame exceeded the "
                f"{CODEX_APP_SERVER_JSONL_LIMIT}-byte safety limit"
            ) from exc
        if not raw:
            stderr = ""
            if include_stderr and self.process.stderr:
                stderr = (await self.process.stderr.read()).decode(errors="replace")
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(f"{closed_message}{detail}")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            await self.stop()
            raise ValueError("Codex app-server emitted malformed JSONL") from exc
        if not isinstance(message, dict):
            await self.stop()
            raise ValueError("Codex app-server JSONL message must be an object")
        return message

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"method": method, "params": params})

    async def _write(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is unavailable")
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()
