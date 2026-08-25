from __future__ import annotations

import hashlib
import re
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


def token_embedding(text: str, dimensions: int = 64) -> list[float]:
    """Create a deterministic local vector for lexical/semantic hybrid search.

    This is intentionally provider-neutral: a configured embedding service can
    replace it later, while generated strategies and imported sources remain
    searchable immediately and reproducibly in the database.
    """
    if dimensions < 8:
        raise ValueError("embedding dimensions too small")
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        for offset in range(0, len(digest), 2):
            index = int.from_bytes(digest[offset : offset + 2], "big") % dimensions
            vector[index] += 1.0 if digest[offset] & 1 else -1.0
    magnitude = sum(value * value for value in vector) ** 0.5
    return [value / magnitude for value in vector] if magnitude else vector


def build_source_data(
    *,
    name: str,
    content: str,
    media_type: str = "text/plain",
    category: str = "general",
    tags: list[str] | None = None,
    source_date: str | None = None,
    version: int = 1,
    source_kind: str = "DOCUMENT",
    source_url: str | None = None,
    external_id: str | None = None,
    asset_class: str | None = None,
    instrument_type: str | None = None,
    venue_instrument_id: str | None = None,
    specification_version_id: str | None = None,
    source_cut_refs: list[str] | None = None,
) -> dict:
    if not content.strip():
        raise ValueError("knowledge source content cannot be empty")
    document_id = UUID(hashlib.sha256(content.encode()).hexdigest()[:32])
    segments = []
    for ordinal, value in enumerate(chunk(content)):
        segment_id = UUID(
            hashlib.sha256(f"{document_id}:{version}:{ordinal}:{value}".encode()).hexdigest()[:32]
        )
        segments.append(
            {
                "id": str(segment_id),
                "document_id": str(document_id),
                "ordinal": ordinal,
                "text": value,
                "version": version,
                "embedding": token_embedding(value),
            }
        )
    return {
        "name": name,
        "media_type": media_type,
        "category": category,
        "tags": sorted(set(tags or [])),
        "source_date": source_date,
        "source_kind": source_kind,
        "source_url": source_url,
        "external_id": external_id,
        "asset_class": asset_class,
        "instrument_type": instrument_type,
        "venue_instrument_id": venue_instrument_id,
        "specification_version_id": specification_version_id,
        "source_cut_refs": sorted(set(source_cut_refs or [])),
        "document_id": str(document_id),
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "generation": version,
        "segments": segments,
        "ingestion_state": "INDEXED",
        "vector_index_state": "INDEXED",
        "embedding_model": "deterministic-hash-v1",
        "segment_count": len(segments),
    }


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
