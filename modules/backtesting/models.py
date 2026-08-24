from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ValidationState(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class ValidationEvidence(BaseModel):
    strategy_version_id: UUID
    stage: str
    state: ValidationState
    metrics: dict[str, float] = {}
    artifact_hash: str


class PaperRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    strategy_version_id: UUID
    signals: int = 0
    trades: int = 0
    state: ValidationState = ValidationState.PENDING
