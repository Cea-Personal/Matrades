from __future__ import annotations

from uuid import UUID

from modules.knowledge.models import KnowledgeSegment, RetrievalHit


async def hybrid_search(
    owner_id: UUID,
    query: str,
    embedder,
    index,
    segments: dict[UUID, KnowledgeSegment],
    limit: int = 5,
) -> list[RetrievalHit]:
    vector = (await embedder.embed([query]))[0]
    raw = await index.search(str(owner_id), vector, limit * 2)
    hits = []
    for segment_id, score in raw:
        item = segments.get(UUID(segment_id))
        if item is None or item.owner_id != owner_id:
            continue
        hits.append(
            RetrievalHit(
                segment_id=item.id,
                document_id=item.document_id,
                source_id=UUID(int=0),
                score=score,
                text=item.text,
                provenance={"document_id": str(item.document_id), "segment": str(item.ordinal)},
            )
        )
    return hits[:limit]
