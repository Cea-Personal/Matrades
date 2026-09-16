"""Optional, explicitly configured reranking of already-authorized retrieval candidates."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.reranking.cohere import DEFAULT_MODEL, MAX_CANDIDATES, cohere_rerank
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import resolve_connection
from packages.shared.store import ResourceStore


class RerankingConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: UUID
    model: Literal["rerank-v4.0-pro", "rerank-v4.0-fast", "rerank-v3.5"] = DEFAULT_MODEL
    candidate_limit: int = Field(default=50, ge=20, le=MAX_CANDIDATES)


async def rerank_for_owner(
    session: AsyncSession, owner_id: UUID, query: str, hits: list[dict], limit: int
) -> tuple[list[dict], dict]:
    """Caller must apply owner, lifecycle and metadata filters before this boundary."""
    records = await ResourceStore(session).list("knowledge_reranking_configuration", owner_id)
    if not records:
        return hits[:limit], {"status": "DISABLED", "provider": None, "model": None}
    configuration = records[0].data
    metadata = {
        "status": "SKIPPED",
        "provider": "COHERE",
        "model": configuration.get("model"),
        "connection_id": configuration.get("connection_id"),
        "configuration_version": records[0].version,
        "candidate_count": 0,
    }
    if not hits:
        return [], metadata
    try:
        settings = RerankingConfigurationInput.model_validate(
            {key: configuration[key] for key in RerankingConfigurationInput.model_fields}
        )
        candidates = hits[: settings.candidate_limit]
        metadata["candidate_count"] = len(candidates)
        connection = await resolve_connection(session, owner_id, settings.connection_id)
        if connection.profile.provider != ConnectionProvider.COHERE or not connection.secret:
            raise RuntimeError("reranking connection unavailable")
        ranked = await cohere_rerank(
            connection.secret,
            query,
            [hit["text"] for hit in candidates],
            model=settings.model,
            top_n=min(limit, len(candidates)),
        )
        return [
            {
                **candidates[index],
                "hybrid_score": candidates[index]["score"],
                "rerank_score": score,
                "score": score,
            }
            for index, score in ranked
        ], {**metadata, "status": "APPLIED"}
    except (LookupError, RuntimeError, ValueError):
        # Failure is visible but cannot remove citations, cross owner boundaries,
        # or silently select a different credential/provider.
        return hits[:limit], {
            **metadata,
            "status": "DEGRADED",
            "reason": "Cohere reranking unavailable; using hybrid retrieval order.",
        }
