from __future__ import annotations

import httpx
import pytest

from traderx.integrations.providers.anthropic_messages import AnthropicMessagesAdapter
from traderx.integrations.providers.openai_responses import OpenAIResponsesAdapter


@pytest.mark.parametrize(
    ("adapter_type", "model_id"),
    [
        (OpenAIResponsesAdapter, "gpt-5.6-luna"),
        (AnthropicMessagesAdapter, "claude-provider-model-20260820"),
    ],
)
def test_fixed_llm_providers_accept_owner_selected_model_ids(
    adapter_type: type[OpenAIResponsesAdapter] | type[AnthropicMessagesAdapter],
    model_id: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/models/{model_id}")
        return httpx.Response(200, json={"id": model_id})

    adapter = adapter_type("write-only-test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = adapter.test_connection(model_id)
    assert result["healthy"] is True
    assert result["model"] == model_id


@pytest.mark.parametrize("adapter_type", [OpenAIResponsesAdapter, AnthropicMessagesAdapter])
def test_llm_adapters_reject_url_shaped_model_ids(
    adapter_type: type[OpenAIResponsesAdapter] | type[AnthropicMessagesAdapter],
) -> None:
    adapter = adapter_type("write-only-test-key", client=httpx.Client())
    with pytest.raises(ValueError, match="model identifier"):
        adapter.test_connection("https://unreviewed.example/model")
