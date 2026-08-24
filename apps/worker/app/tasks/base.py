from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TaskEnvelope:
    job_id: UUID
    owner_id: UUID
    correlation_id: UUID
    idempotency_key: str
    attempt: int = 1


def retry_delay(attempt: int, cap: int = 300) -> int:
    return int(min(2 ** max(0, attempt - 1), cap))
