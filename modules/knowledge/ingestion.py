from __future__ import annotations

import hashlib
from uuid import UUID

from modules.knowledge.models import KnowledgeDocument, KnowledgeSegment


def chunk(text: str, max_chars: int = 1000) -> list[str]:
    if max_chars < 100:
        raise ValueError("chunk size too small")
    return [
        text[i : i + max_chars]
        for i in range(0, len(text), max_chars)
        if text[i : i + max_chars].strip()
    ]


async def ingest(
    owner_id: UUID, source_id: UUID, name: str, text: str, embedder, index
) -> tuple[KnowledgeDocument, list[KnowledgeSegment]]:
    digest = hashlib.sha256(text.encode()).hexdigest()
    document = KnowledgeDocument(
        source_id=source_id, owner_id=owner_id, name=name, content_hash=digest
    )
    segments = [
        KnowledgeSegment(document_id=document.id, owner_id=owner_id, text=value, ordinal=i)
        for i, value in enumerate(chunk(text))
    ]
    vectors = await embedder.embed([x.text for x in segments])
    segments = [
        x.model_copy(update={"embedding": vector})
        for x, vector in zip(segments, vectors, strict=True)
    ]
    await index.upsert(str(owner_id), [(str(x.id), x.embedding or []) for x in segments])
    return document, segments
