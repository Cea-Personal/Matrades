from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from modules.knowledge.models import KnowledgeSegment, RetrievalHit


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorIndexPort(Protocol):
    async def upsert(self, owner_id: str, segments: list[KnowledgeSegment]) -> None: ...

    async def search(
        self, owner_id: str, vector: list[float], limit: int
    ) -> list[tuple[str, float]]: ...


class JournalIndexWork(BaseModel):
    id: UUID
    owner_id: UUID
    journal_entry_id: UUID
    state: str = "QUEUED"
    generation: int = 1


class RetrievalPort(Protocol):
    async def search(self, owner_id: UUID, query: str, limit: int = 5) -> list[RetrievalHit]: ...
