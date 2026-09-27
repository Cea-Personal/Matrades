"""Shared, audited knowledge retrieval for API and background researchers.

Retrieved text is untrusted context, never market facts or execution authority.
Workers receive bounded evidence instead of fictitious callable tool permissions.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from modules.knowledge.openai_embeddings import embed_texts_for_owner
from modules.knowledge.reranking import rerank_for_owner
from packages.shared.store import ResourceStore


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_date_from: str | None = None
    source_date_to: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    asset_class: str | None = None
    instrument_type: str | None = None
    venue_instrument_id: str | None = None


# Keep the public OpenAPI schema name stable while exposing a domain-specific alias.
KnowledgeSearchInput = SearchInput


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return dot / norm if norm else 0.0


async def retrieve_knowledge(
    session: AsyncSession,
    owner_id: UUID,
    payload: KnowledgeSearchInput,
    *,
    actor_id: UUID | None = None,
    source_id: UUID | None = None,
    research: bool = False,
) -> dict[str, Any]:
    store = ResourceStore(session)
    sources = [
        source
        for source in await store.list("knowledge_source", owner_id)
        if source.state == "ACTIVE" and (source_id is None or source.id == source_id)
    ]
    filtered = []
    for source in sources:
        data = source.data
        if payload.category and data.get("category") != payload.category:
            continue
        if not set(payload.tags).issubset(data.get("tags", [])):
            continue
        if any(
            value and data.get(field) != value and not (research and not data.get(field))
            for field, value in (
                ("asset_class", payload.asset_class),
                ("instrument_type", payload.instrument_type),
                ("venue_instrument_id", payload.venue_instrument_id),
            )
        ):
            continue
        source_date = data.get("source_date")
        if payload.source_date_from and source_date and source_date < payload.source_date_from:
            continue
        if payload.source_date_to and source_date and source_date > payload.source_date_to:
            continue
        if data.get("segments"):
            filtered.append(source)
    embedding = {"status": "SKIPPED", "model": None}
    vector: list[float] = []
    model = ""
    if filtered:
        try:
            vectors, model = await embed_texts_for_owner(session, owner_id, [payload.query])
            vector = vectors[0]
            embedding = {"status": "APPLIED", "model": model}
        except (LookupError, RuntimeError, ValueError, httpx.HTTPError):
            embedding = {"status": "DEGRADED", "model": None}
    terms = set(re.findall(r"[a-z0-9]+", payload.query.lower()))
    hits: list[dict[str, Any]] = []
    for source in filtered:
        source_model = str(source.data.get("embedding_model") or "")
        compatible = source_model == model
        for segment in source.data["segments"]:
            text = str(segment["text"])
            overlap = len(terms & set(re.findall(r"[a-z0-9]+", text.lower())))
            lexical_score = overlap / max(len(terms), 1)
            vector_score = (
                max(0.0, _cosine(vector, segment.get("embedding", []))) if compatible else 0.0
            )
            if not overlap and vector_score < 0.08 and source_id is None:
                continue
            hits.append(
                {
                    "reference_id": f"knowledge:{segment['id']}",
                    "source_id": str(source.id),
                    "source_name": source.data.get("name"),
                    "source_kind": source.data.get("source_kind"),
                    "source_url": source.data.get("source_url"),
                    "document_id": segment["document_id"],
                    "segment_id": segment["id"],
                    "segment_ordinal": segment["ordinal"],
                    "source_version": source.version,
                    "source_date": source.data.get("source_date"),
                    "score": 0.65 * lexical_score + 0.35 * vector_score,
                    "lexical_score": lexical_score,
                    "vector_score": vector_score,
                    "embedding_model": source_model,
                    "text": text,
                    "authority": "CONTEXT_ONLY",
                }
            )
    hits.sort(key=lambda hit: (-hit["score"], str(hit["source_name"]), hit["segment_ordinal"]))
    if research and source_id is None:
        # Do not allow a long recent transcript to consume the entire candidate pool.
        counts: dict[str, int] = {}
        diversified = []
        for hit in hits:
            key = hit["source_id"]
            counts[key] = counts.get(key, 0) + 1
            if counts[key] <= 3:
                diversified.append(hit)
        hits = diversified
    hits, reranking = await rerank_for_owner(session, owner_id, payload.query, hits, payload.limit)
    if research:
        hits = [{**hit, "text": hit["text"][:1200]} for hit in hits]
    audit = await store.audit(
        owner_id,
        actor_id,
        "knowledge.retrieved",
        "knowledge_search",
        None,
        {
            "query_hash": hashlib.sha256(payload.query.encode()).hexdigest(),
            "result_segment_ids": [hit["segment_id"] for hit in hits],
            "reranking": reranking,
            "embedding": embedding,
            "access_mode": "BACKEND_RETRIEVAL" if research else "API_RETRIEVAL",
            "pinned_source_id": str(source_id) if source_id else None,
        },
    )
    return {
        "authority": "CONTEXT_ONLY",
        "may_replace_facts": False,
        "retrieval_audit_id": str(audit.id),
        "citations": hits,
        "reranking": reranking,
        "embedding": embedding,
        "access_mode": "BACKEND_RETRIEVAL" if research else "API_RETRIEVAL",
        "agent_callable_tools": [],
    }
