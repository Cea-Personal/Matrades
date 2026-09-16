import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from adapters.reranking.cohere import cohere_rerank
from modules.connections.models import ConnectionProfile, ConnectionProvider
from modules.connections.testing import probe_connection
from modules.knowledge.reranking import RerankingConfigurationInput


async def test_cohere_v2_request_and_index_mapping():
    async def handler(request):
        assert str(request.url) == "https://api.cohere.com/v2/rerank"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {
            "model": "rerank-v4.0-fast",
            "query": "risk evidence",
            "documents": ["first", "second", "third"],
            "top_n": 2,
            "max_tokens_per_doc": 4096,
        }
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "index": 2,
                        "relevance_score": 0.98,
                        "document": {"text": "untrusted replacement"},
                    },
                    {"index": 0, "relevance_score": 0.42},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await cohere_rerank(
            "test-key",
            "risk evidence",
            ["first", "second", "third"],
            model="rerank-v4.0-fast",
            top_n=2,
            client=client,
        ) == [(2, 0.98), (0, 0.42)]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"results": []},
        {"results": "wrong"},
        {"results": [None]},
        {"results": [{"index": -1, "relevance_score": 0.9}]},
        {"results": [{"index": 2, "relevance_score": 0.9}]},
        {"results": [{"index": True, "relevance_score": 0.9}]},
        {"results": [{"index": 0, "relevance_score": "0.9"}]},
        {"results": [{"index": 0, "relevance_score": 2}]},
        {"results": [{"index": 0, "relevance_score": True}]},
    ],
)
async def test_malformed_response_is_rejected(body):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    ) as client:
        with pytest.raises(RuntimeError, match="invalid reranking response"):
            await cohere_rerank("key", "query", ["document"], top_n=1, client=client)


async def test_duplicate_results_are_rejected():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 0, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.8},
                    ]
                },
            )
        )
    ) as client:
        with pytest.raises(RuntimeError, match="invalid reranking response"):
            await cohere_rerank("key", "query", ["first", "second"], top_n=2, client=client)


@pytest.mark.parametrize("status", [401, 429, 500, 302])
async def test_provider_failure_never_exposes_response_or_key(status):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"message": "test-secret private document"})
        )
    ) as client:
        with pytest.raises(RuntimeError) as error:
            await cohere_rerank(
                "test-secret", "query", ["private document"], top_n=1, client=client
            )
    assert str(status) in str(error.value)
    assert "test-secret" not in str(error.value)
    assert "private document" not in str(error.value)


async def test_timeout_is_safe():
    def handler(request):
        raise httpx.ReadTimeout("sensitive error", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="unavailable or timed out") as error:
            await cohere_rerank("key", "query", ["document"], top_n=1, client=client)
        assert "sensitive" not in str(error.value)


async def test_probe_uses_synthetic_text_and_advertises_reranking():
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer key"
        payload = json.loads(request.content)
        assert payload["top_n"] == 1
        assert payload["documents"] == [
            "Knowledge retrieval finds relevant evidence for a question."
        ]
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]})

    profile = ConnectionProfile(name="Cohere", provider="COHERE", credential_id=uuid4())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "key", client=client)
    assert result.status == "HEALTHY"
    assert result.writes is False
    assert "knowledge.rerank" in result.capabilities


def test_configuration_requires_credentials_and_bounded_candidate_pool():
    with pytest.raises(ValidationError):
        ConnectionProfile(name="Cohere", provider=ConnectionProvider.COHERE)
    for limit in [0, 19, 101]:
        with pytest.raises(ValidationError):
            RerankingConfigurationInput(connection_id=uuid4(), candidate_limit=limit)
    with pytest.raises(ValidationError):
        RerankingConfigurationInput(connection_id=uuid4(), model="unsupported")
