"""Bounded Cohere v2 reranking; provider output may reorder, never replace, evidence."""

from __future__ import annotations

import math

import httpx

DEFAULT_MODEL = "rerank-v4.0-pro"
SUPPORTED_MODELS = (DEFAULT_MODEL, "rerank-v4.0-fast", "rerank-v3.5")
MAX_CANDIDATES = 100


async def cohere_rerank(
    api_key: str,
    query: str,
    documents: list[str],
    *,
    model: str = DEFAULT_MODEL,
    top_n: int = 5,
    client: httpx.AsyncClient | None = None,
) -> list[tuple[int, float]]:
    if (
        not api_key
        or not query.strip()
        or not documents
        or any(not text.strip() for text in documents)
    ):
        raise ValueError("reranking requires a credential, query and non-empty documents")
    if (
        model not in SUPPORTED_MODELS
        or len(documents) > MAX_CANDIDATES
        or not 1 <= top_n <= len(documents)
    ):
        raise ValueError("invalid reranking model or candidate limits")
    http = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        response = await http.post(
            "https://api.cohere.com/v2/rerank",
            follow_redirects=False,
            headers={"Authorization": f"Bearer {api_key}", "X-Client-Name": "Matrades"},
            json={
                "model": model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "max_tokens_per_doc": 4096,
            },
        )
        if response.status_code != 200:
            # Do not expose provider bodies, which can echo credentials or source text.
            raise RuntimeError(f"Cohere reranking request failed ({response.status_code})")
        try:
            body = response.json()
            results = body["results"]
            if not isinstance(results, list) or len(results) != top_n:
                raise ValueError("incomplete results")
            ranked: list[tuple[int, float]] = []
            seen: set[int] = set()
            for item in results:
                index, score = item["index"], item["relevance_score"]
                if (
                    type(index) is not int
                    or index not in range(len(documents))
                    or index in seen
                    or type(score) not in (int, float)
                    or not math.isfinite(score)
                    or not 0 <= score <= 1
                ):
                    raise ValueError("invalid result")
                seen.add(index)
                ranked.append((index, float(score)))
            return sorted(ranked, key=lambda item: -item[1])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Cohere returned an invalid reranking response") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Cohere reranking is unavailable or timed out") from exc
    finally:
        if client is None:
            await http.aclose()
