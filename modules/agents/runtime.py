from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

from adapters.agent_runtime.codex_app_server.client import CodexAppServerClient
from adapters.agent_runtime.litellm.client import LiteLLMClient
from adapters.agent_runtime.result import RuntimeResult
from modules.agents.execution_audit import ExecutionAudit
from modules.agents.models import (
    AgentDefinition,
    AgentExecution,
    ExecutionStatus,
    ModelProfile,
    RuntimeType,
)
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import ResolvedPrompts
from modules.agents.runtime_context import validate_typed_context
from packages.shared.config import get_settings


class RuntimeClient(Protocol):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AgentRuntimeRouter:
    def __init__(
        self,
        clients: dict[RuntimeType, RuntimeClient] | None = None,
        audit: ExecutionAudit | None = None,
    ) -> None:
        self.clients = clients or {}
        self.audit = audit or ExecutionAudit()
        self.running = False

    @classmethod
    def from_settings(cls, overrides: dict[str, Any] | None = None) -> AgentRuntimeRouter:
        settings = get_settings()
        overrides = overrides or {}
        codex_enabled = bool(overrides.get("codex_enabled", settings.codex_enabled))
        litellm_enabled = bool(overrides.get("litellm_enabled", settings.litellm_enabled))
        litellm_url = str(overrides.get("litellm_url", settings.litellm_url))
        litellm_api_key = overrides.get("litellm_api_key", settings.litellm_api_key)
        clients: dict[RuntimeType, RuntimeClient] = {}
        if codex_enabled:
            clients[RuntimeType.CODEX_APP_SERVER] = CodexAppServerClient(
                settings.codex_binary,
                Path.cwd(),
            )
        if litellm_enabled and litellm_api_key:
            if hasattr(litellm_api_key, "get_secret_value"):
                litellm_api_key = litellm_api_key.get_secret_value()
            clients[RuntimeType.LITELLM_GATEWAY] = LiteLLMClient(litellm_url, str(litellm_api_key))
        return cls(clients)

    async def start(self) -> None:
        for client in self.clients.values():
            start = getattr(client, "start", None)
            if start:
                await start()
        self.running = True

    async def stop(self) -> None:
        for client in self.clients.values():
            stop = getattr(client, "stop", None)
            if stop:
                await stop()
        self.running = False

    async def close(self) -> None:
        await self.stop()

    async def execute(
        self,
        agent: AgentDefinition,
        profiles: dict,
        prompts: ResolvedPrompts,
        permissions: PermissionSet,
        payload: dict[str, Any],
        deadline_seconds: float = 30,
        orchestrator_profile: ModelProfile | None = None,
    ) -> tuple[AgentExecution, dict[str, Any] | None]:
        validate_typed_context(agent, payload)
        profile: ModelProfile = profiles[agent.profile_id]
        if profile.runtime != agent.runtime:
            raise ValueError("runtime/profile mismatch")
        if (
            agent.runtime == RuntimeType.CODEX_APP_SERVER
            and orchestrator_profile is not None
            and orchestrator_profile.runtime != RuntimeType.CODEX_APP_SERVER
        ):
            raise ValueError("Codex specialists require a Codex orchestrator profile")
        candidates = [profile] + [profiles[item] for item in profile.fallback_profile_ids]
        if any(item.runtime != agent.runtime for item in candidates):
            raise ValueError("cross-runtime fallback prohibited")
        started = monotonic()
        deadline = started + max(1.0, deadline_seconds)
        result = None
        actual = profile
        error = None
        evidence: RuntimeResult | None = None
        fallback_reason = None
        client = self.clients.get(agent.runtime)
        if client is None:
            status, error = ExecutionStatus.BLOCKED, "selected runtime unavailable"
        else:
            status = ExecutionStatus.FAILED
            for actual in candidates:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    result = None
                    error = "agent runtime deadline exceeded"
                    break
                try:
                    result = await asyncio.wait_for(
                        client.invoke(
                            {
                                "input": payload,
                                "agent_role": agent.logical_id,
                                "model": actual.model,
                                "reasoning_effort": actual.parameters.get("reasoning_effort"),
                                "orchestrator_model": (
                                    orchestrator_profile.model if orchestrator_profile else None
                                ),
                                "orchestrator_reasoning_effort": (
                                    orchestrator_profile.parameters.get("reasoning_effort")
                                    if orchestrator_profile
                                    else None
                                ),
                                "system": prompts.system,
                                "user": prompts.user,
                                "tools": permissions.tools,
                                "output_schema": payload.get("output_schema"),
                            }
                        ),
                        remaining,
                    )
                    if not isinstance(result, dict):
                        raise ValueError("invalid runtime response schema")
                    evidence = result if isinstance(result, RuntimeResult) else None
                    status, error = ExecutionStatus.SUCCEEDED, None
                    break
                except (TimeoutError, ValueError, RuntimeError) as exc:
                    # Do not let a failed candidate leak a stale/non-structured
                    # value into the worker response.
                    result = None
                    error = str(exc)
                    if actual.id == profile.id:
                        fallback_reason = error
            if result is None:
                status = ExecutionStatus.DEGRADED
        execution = AgentExecution(
            logical_id=agent.logical_id,
            selected_runtime=agent.runtime,
            actual_runtime=agent.runtime,
            selection_source=(
                "native_agent"
                if profile.parameters.get("assignment") == "native_agent"
                else "agent_profile"
            ),
            configured_model=profile.model,
            requested_model=actual.model,
            actual_model=evidence.actual_model if evidence else None,
            model_verified=bool(evidence and evidence.actual_model),
            model_evidence_source=evidence.model_evidence_source if evidence else None,
            orchestrator_model=evidence.orchestrator_model if evidence else None,
            fallback_reason=fallback_reason if actual.id != profile.id else None,
            resolved_system_prompt=prompts.system,
            resolved_user_prompt=prompts.user,
            tools=permissions.tools,
            status=status,
            duration_ms=int((monotonic() - started) * 1000),
            error=error,
        )
        self.audit.record(execution)
        return execution, result
