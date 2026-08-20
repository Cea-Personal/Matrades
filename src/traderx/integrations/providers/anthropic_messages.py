from __future__ import annotations

import json

import httpx

from traderx.integrations.ports import LlmAnalysisRequest, LlmAnalysisResponse
from traderx.integrations.registry import approved_provider
from traderx.market_research.llm_schema import advisory_json_schema


class AnthropicMessagesAdapter:
    provider = "ANTHROPIC_MESSAGES"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 180,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Anthropic API key is required")
        definition = approved_provider(self.provider)
        assert definition.fixed_base_url is not None
        self._api_key = api_key
        self._base_url = definition.fixed_base_url.rstrip("/")
        self._models = definition.permitted_models
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def test_connection(self, exact_model_id: str) -> dict[str, object]:
        self._require_model(exact_model_id)
        try:
            response = self._client.get(
                f"{self._base_url}/models/{exact_model_id}", headers=self._headers()
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return {"healthy": False, "model": exact_model_id, "reason": "NETWORK_FAILURE"}
        return {
            "healthy": response.status_code < 400,
            "model": exact_model_id,
            "status_code": response.status_code,
        }

    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse:
        self._validate_request(request)
        body: dict[str, object] = {
            "model": request.exact_model_id,
            "max_tokens": 1200,
            "system": (
                "Analyze only normalized market evidence. Return JSON matching this schema: "
                f"{json.dumps(advisory_json_schema(), sort_keys=True)}. The analysis is advisory "
                "and cannot alter deterministic results or trigger financial actions."
            ),
            "messages": [
                {"role": "user", "content": json.dumps(request.evidence, sort_keys=True)}
            ],
        }
        try:
            response = self._client.post(
                f"{self._base_url}/messages",
                headers=self._headers(),
                json=body,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException:
            return LlmAnalysisResponse("TIMED_OUT", None, reason="TIMED_OUT")
        except httpx.NetworkError:
            return LlmAnalysisResponse("FAILED", None, reason="TRANSIENT_PROVIDER_FAILURE")
        request_id = response.headers.get("request-id")
        if response.status_code == 429:
            return LlmAnalysisResponse(
                "RATE_LIMITED",
                None,
                provider_request_id=request_id,
                retry_after_seconds=_retry_after(response),
                reason="RATE_LIMIT",
            )
        if response.status_code >= 400:
            return LlmAnalysisResponse(
                "FAILED", None, provider_request_id=request_id, reason=f"PROVIDER_HTTP_{response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return LlmAnalysisResponse(
            "COMPLETED",
            _anthropic_analysis(payload),
            provider_request_id=request_id,
            usage=_usage(payload.get("usage")),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _require_model(self, model: str) -> None:
        if model not in self._models:
            raise ValueError("model is outside the reviewed Anthropic allowlist")

    def _validate_request(self, request: LlmAnalysisRequest) -> None:
        if request.provider != self.provider:
            raise ValueError("analysis request provider does not match this adapter")
        self._require_model(request.exact_model_id)
        if request.store:
            raise ValueError("market research analysis must not request provider storage")


def _anthropic_analysis(payload: dict[str, object]) -> dict[str, object] | None:
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            try:
                parsed = json.loads(block["text"])
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def _usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int(item)
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool)
    }


def _retry_after(response: httpx.Response) -> int | None:
    try:
        return int(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
