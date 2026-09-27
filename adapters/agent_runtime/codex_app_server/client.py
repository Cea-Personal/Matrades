from __future__ import annotations

import asyncio
import json
import logging
import re
import tomllib
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from adapters.agent_runtime.result import RuntimeResult
from modules.agents.native_config import REASONING_EFFORTS, load_native_agent

CODEX_APP_SERVER_JSONL_LIMIT = 8 * 1024 * 1024
logger = logging.getLogger(__name__)


class CodexAppServerClient:
    """Supervises the official JSONL stdio app-server protocol."""

    runtime_type = "CODEX_APP_SERVER"

    def __init__(
        self,
        binary: str = "codex",
        cwd: Path | None = None,
        native_agents_dir: Path | None = None,
        orchestrator_model: str | None = None,
    ) -> None:
        self.binary = binary
        self.cwd = cwd or Path.cwd()
        self.native_agents_dir = native_agents_dir or self.cwd / ".codex" / "agents"
        self.orchestrator_model = orchestrator_model
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._pending_notifications: deque[dict[str, Any]] = deque()

    @property
    def healthy(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        if self.healthy:
            return
        # The image contains the project-scoped .codex/agents directory but no
        # .git directory. Codex otherwise treats /app as untrusted and silently
        # skips that role configuration. Trust only this concrete application
        # workspace, never a parent or arbitrary directory.
        project_config = (
            ["-c", f'projects.{json.dumps(str(self.cwd.resolve()))}.trust_level="trusted"']
            if self.native_agents_dir.is_dir()
            else []
        )
        self.process = await asyncio.create_subprocess_exec(
            self.binary,
            "app-server",
            *project_config,
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
        # A private per-invocation role layer makes explicit saved profiles work
        # without editing the user's native files or changing another slot's role.
        async with self._lock:
            with TemporaryDirectory(prefix="matrades-agent-") as snapshot_dir:
                try:
                    return await self._invoke_configured(payload, Path(snapshot_dir))
                finally:
                    self._pending_notifications.clear()

    async def _invoke_configured(
        self, payload: dict[str, Any], snapshot_dir: Path
    ) -> RuntimeResult:
        await self.start()
        logical_id = str(payload.get("agent_role", "")).strip()
        orchestrator = load_native_agent("orchestrator", self.native_agents_dir)
        parent_model = (
            payload.get("orchestrator_model") or self.orchestrator_model or orchestrator["model"]
        )
        parent_effort = (
            payload.get("orchestrator_reasoning_effort") or orchestrator["model_reasoning_effort"]
        )
        instructions = orchestrator["developer_instructions"]
        config: dict[str, Any] = {"model_reasoning_effort": parent_effort}
        if logical_id == "orchestrator":
            parent_model = payload.get("model") or parent_model
            parent_effort = payload.get("reasoning_effort") or parent_effort
            config["model_reasoning_effort"] = parent_effort
        if (
            not isinstance(parent_model, str)
            or not parent_model.strip()
            or not isinstance(parent_effort, str)
            or parent_effort not in REASONING_EFFORTS
        ):
            raise ValueError("invalid orchestrator model profile settings")
        if logical_id and logical_id != "orchestrator":
            role = load_native_agent(logical_id, self.native_agents_dir)
            role_model = payload.get("model") or role["model"]
            role_effort = payload.get("reasoning_effort") or role["model_reasoning_effort"]
            snapshot = self._snapshot_role(logical_id, role, role_model, role_effort, snapshot_dir)
            # App Server's thread-scoped config supports the legacy role
            # config_file layer as well as automatically discovered files.
            config[f"agents.{logical_id}.config_file"] = str(snapshot)
            config[f"agents.{logical_id}.description"] = role["description"]
            instructions += (
                "\nCURRENT PARENT-ONLY ROUTE: Call spawn_agent exactly once with "
                f'agent_type="{logical_id}" and fork_context=true, then wait for '
                "the child. The inherited user turn is the specialist's task, not "
                "an instruction for the child to delegate. If you are the spawned "
                "specialist, perform the review yourself and do not spawn again."
            )
        thread = await self._request(
            "thread/start",
            {
                "model": parent_model,
                "config": config,
                "cwd": str(self.cwd),
                # The application owns the top-level orchestration contract. The
                # requested logical role is then delegated through Codex's native
                # spawn_agent tool, which resolves its project-scoped TOML role.
                "developerInstructions": instructions,
                "approvalPolicy": "never",
                # Codex App Server uses kebab-case sandbox policy values.
                # Keep this read-only: research agents must not write files
                # or perform broker/execution actions.
                "sandbox": "read-only",
                "serviceName": "matrades",
                # Context inheritance requires a non-ephemeral parent in
                # the installed Codex App Server. Delete it in finally.
                "ephemeral": False,
            },
        )
        thread_id = thread["thread"]["id"]
        try:
            result = await self._invoke_thread(
                payload, logical_id, thread_id, parent_model, parent_effort
            )
            # A requested spawn model is NOT execution proof. Read the actual
            # completed thread's turn context before deleting its evidence.
            result.orchestrator_model = await asyncio.to_thread(
                self._rollout_model, thread["thread"].get("path"), thread_id
            )
            if logical_id == "orchestrator":
                result.actual_model = result.orchestrator_model
                if result.actual_model:
                    result.model_evidence_source = "codex_turn_context"
            return result
        finally:
            # Non-ephemeral parent/child sessions contain market evidence.
            # Always remove them, including on timeout or malformed output.
            cleanup = asyncio.create_task(self._request("thread/delete", {"threadId": thread_id}))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                # Hold the per-client lock until cleanup finishes; otherwise
                # the next lane could consume this request's reply.
                try:
                    await cleanup
                except Exception:
                    logger.warning("Codex research thread cleanup failed", exc_info=True)
                raise
            except Exception:
                logger.warning("Codex research thread cleanup failed", exc_info=True)

    async def _invoke_thread(
        self,
        payload: dict[str, Any],
        logical_id: str,
        thread_id: str,
        parent_model: str | None = None,
        parent_effort: str | None = None,
    ) -> RuntimeResult:
        prompt = (
            f"SYSTEM CONTRACT:\n{payload.get('system', '')}\n\n"
            f"USER CONTRACT:\n{payload.get('user', '')}\n\n"
            "Return only one JSON object matching the requested output schema. "
            "Do not run commands, modify files, access credentials, or perform "
            "broker actions.\n\n"
            f"OUTPUT SCHEMA:\n{json.dumps(payload.get('output_schema') or {}, default=str)}\n\n"
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
            "model": parent_model
            or load_native_agent("orchestrator", self.native_agents_dir)["model"],
        }
        if parent_effort:
            params["effort"] = parent_effort
        if payload.get("output_schema"):
            params["outputSchema"] = payload["output_schema"]
        turn = await self._request("turn/start", params)
        turn_id = turn["turn"]["id"]
        final_messages: list[str] = []
        unphased_messages: list[str] = []
        delegated = False
        child_ids: set[str] = set()
        collaboration_events: list[str] = []
        assert self.process is not None and self.process.stdout is not None
        while True:
            if self._pending_notifications:
                message = self._pending_notifications.popleft()
            else:
                message = await self._read_message(
                    read_timeout_seconds=120,
                    closed_message="Codex app-server exited before turn completion",
                    include_stderr=True,
                )
            method = message.get("method")
            params_value = message.get("params", {})
            if method == "item/completed":
                if params_value.get("threadId", thread_id) != thread_id:
                    continue
                if params_value.get("turnId", turn_id) != turn_id:
                    continue
                item = params_value.get("item", {})
                if item.get("type") in {"collabToolCall", "collabAgentToolCall"}:
                    tool = str(item.get("tool", ""))
                    status = str(item.get("status", ""))
                    collaboration_events.append(f"{tool}:{status}"[:80])
                    if tool in {"spawn_agent", "spawnAgent"} and status in {
                        "completed",
                        "succeeded",
                    }:
                        delegated = True
                        child_ids.update(item.get("receiverThreadIds") or [])
                if item.get("type") == "agentMessage" and item.get("text"):
                    if item.get("phase") == "final_answer":
                        final_messages.append(str(item["text"]))
                    elif not item.get("phase"):
                        # Older app-server releases did not label the final
                        # item. In that case only the last complete message
                        # can be the result, never a concatenation of items.
                        unphased_messages.append(str(item["text"]))
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
        # Deltas and commentary are not the final response. Native subagent
        # delegation can emit several complete agent messages in one turn;
        # joining them makes even valid JSON outputs unparseable.
        if logical_id and logical_id != "orchestrator" and not delegated:
            raise RuntimeError(
                f"Codex did not complete native spawn_agent delegation for {logical_id} "
                f"(collaboration events: {', '.join(collaboration_events) or 'none'})"
            )
        text = (final_messages or unphased_messages or [""])[-1].strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Codex response was not valid structured JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("Codex response must be a JSON object")
        evidence = RuntimeResult(result)
        if len(child_ids) > 1:
            raise RuntimeError("Codex spawned more than one specialist for a bounded request")
        for child_id in child_ids:
            try:
                child = await asyncio.wait_for(
                    self._request("thread/read", {"threadId": child_id}), timeout=2
                )
                metadata = child.get("thread", {})
                if metadata.get("id") != child_id:
                    continue
                if metadata.get("agentRole") not in {None, logical_id}:
                    continue
                evidence.actual_model = await asyncio.to_thread(
                    self._rollout_model, metadata.get("path"), child_id, turn_id
                )
                if evidence.actual_model:
                    evidence.model_evidence_source = "codex_turn_context"
            except (OSError, ValueError, RuntimeError, TimeoutError):
                # Older servers may not expose child rollout metadata. Preserve
                # the research result but leave the execution model unverified.
                logger.warning("Codex child model evidence unavailable for %s", logical_id)
        return evidence

    def _snapshot_role(
        self,
        logical_id: str,
        role: dict[str, Any],
        model: str,
        effort: str,
        directory: Path,
    ) -> Path:
        if (
            not isinstance(model, str)
            or not model.strip()
            or not isinstance(effort, str)
            or effort not in REASONING_EFFORTS
        ):
            raise ValueError("invalid model profile settings")
        source = (self.native_agents_dir / f"{logical_id}.toml").read_text()
        for key, value in (("model", model), ("model_reasoning_effort", effort)):
            replacement = f"{key} = {json.dumps(value)}"
            source, count = re.subn(
                rf"(?m)^[ \t]*{key}\s*=.*$",
                replacement.replace("\\", "\\\\"),
                source,
                count=1,
            )
            if count != 1:
                raise ValueError(f"Native agent {logical_id} has no top-level {key}")
        # Reject concurrent edits and ensure profile overrides cannot change
        # instructions, sandbox, tools or any other native session setting.
        expected = {**role, "model": model, "model_reasoning_effort": effort}
        if tomllib.loads(source) != expected:
            raise ValueError("Native agent changed while preparing its model settings; retry")
        path = directory / f"{logical_id}.toml"
        path.write_text(source)
        return path

    @staticmethod
    def _rollout_model(
        path: Any, thread_id: str, inherited_turn_id: str | None = None
    ) -> str | None:
        """Read only the server-reported thread's bounded JSONL turn metadata."""
        if not isinstance(path, str) or not isinstance(thread_id, str):
            return None
        file = Path(path)
        if not file.is_absolute() or not file.name.endswith(f"-{thread_id}.jsonl"):
            return None
        model = None
        try:
            if file.stat().st_size > 16 * 1024 * 1024:
                return None
            with file.open() as stream:
                for line in stream:
                    item = json.loads(line)
                    payload = item.get("payload", {})
                    if item.get("type") == "session_meta" and payload.get("id") not in {
                        None,
                        thread_id,
                    }:
                        return None
                    if item.get("type") == "turn_context":
                        # Forked child rollouts may contain the parent's context;
                        # that is not proof of a specialist execution.
                        if inherited_turn_id and payload.get("turn_id") in {
                            None,
                            inherited_turn_id,
                        }:
                            model = None
                            continue
                        value = payload.get("model")
                        if isinstance(value, str) and value.strip():
                            model = value
        except (OSError, ValueError, AttributeError):
            return None
        return model

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
                if message.get("method"):
                    self._pending_notifications.append(message)
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
