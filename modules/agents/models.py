from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AwareDateTime, ResearchLaneKey, utc_now


class RuntimeType(StrEnum):
    CODEX_APP_SERVER = "CODEX_APP_SERVER"
    LITELLM_GATEWAY = "LITELLM_GATEWAY"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ModelProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    runtime: RuntimeType
    provider: str
    model: str
    fallback_profile_ids: list[UUID] = []
    parameters: dict[str, Any] = {}
    capabilities: set[str] = set()
    active: bool = True


class AgentDefinition(BaseModel):
    logical_id: str
    required: bool = True
    runtime: RuntimeType = RuntimeType.CODEX_APP_SERVER
    profile_id: UUID | None = None
    system_prompt_override: str | None = None
    user_prompt_override: str | None = None
    permission_set_version: str = "v1"
    required_lanes: tuple[ResearchLaneKey, ...] = ()
    structured_output_required: bool = True
    capability_declarations: tuple[str, ...] = ()


class AgentExecution(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    logical_id: str
    selected_runtime: RuntimeType
    actual_runtime: RuntimeType
    selection_source: str
    configured_model: str
    actual_model: str
    fallback_reason: str | None = None
    resolved_system_prompt: str
    resolved_user_prompt: str
    tools: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    status: ExecutionStatus
    duration_ms: int
    error: str | None = None
    created_at: AwareDateTime = Field(default_factory=utc_now)
