from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AwareDateTime, utc_now


class SourceState(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETED = "DELETED"
    DEGRADED = "DEGRADED"


class KnowledgeSource(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    state: SourceState = SourceState.ACTIVE
    tags: set[str] = set()
    version: int = 1


class KnowledgeDocument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    owner_id: UUID
    name: str
    content_hash: str
    version: int = 1
    created_at: AwareDateTime = Field(default_factory=utc_now)


class KnowledgeSegment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    owner_id: UUID
    text: str
    ordinal: int
    embedding: list[float] | None = None


class RetrievalHit(BaseModel):
    segment_id: UUID
    document_id: UUID
    source_id: UUID
    score: float
    text: str
    provenance: dict[str, str]
