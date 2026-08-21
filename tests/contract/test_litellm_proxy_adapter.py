from __future__ import annotations

import json

import httpx

from traderx.integrations.ports import LlmAnalysisRequest
from traderx.integrations.providers.litellm_proxy import LiteLlmProxyAdapter
from traderx.market_research.llm_schema import advisory_json_schema


def test_advisory_schema_is_compatible_with_openai_strict_json_mode() -> None:
    schema = advisory_json_schema()
    assert set(schema["required"]) == {
        "summary",
        "anomalies",
        "cautions",
        "method_proposals",
    }


def test_litellm_proxy_uses_only_openai_compatible_advisory_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-write-only-virtual-key"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "openrouter/google/gemini-2.5-pro"}]})
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "openrouter/google/gemini-2.5-pro"
        assert body["tools"] == []
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "id": "litellm-request-1",
                "choices": [{"message": {"content": '{"summary":"advisory only"}'}}],
                "usage": {"total_tokens": 7},
            },
        )

    adapter = LiteLlmProxyAdapter(
        "write-only-virtual-key",
        base_url="https://gateway.example/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert adapter.test_connection() == {"healthy": True}
    assert adapter.test_connection("openrouter/google/gemini-2.5-pro") == {
        "healthy": True,
        "model": "openrouter/google/gemini-2.5-pro",
    }
    result = adapter.analyze(
        LlmAnalysisRequest(
            provider="LITELLM_PROXY",
            exact_model_id="openrouter/google/gemini-2.5-pro",
            prompt_template_version="test",
            output_schema_version="test",
            inference_policy_version="test",
            evidence={"category": "FOREX"},
        )
    )
    assert result.state == "COMPLETED"
    assert result.analysis == {"summary": "advisory only"}
