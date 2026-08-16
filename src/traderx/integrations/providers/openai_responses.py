from __future__ import annotations

import json

import httpx

from traderx.integrations.ports import LlmAnalysisRequest, LlmAnalysisResponse
from traderx.integrations.registry import approved_provider
from traderx.market_research.llm_schema import advisory_json_schema


class OpenAIResponsesAdapter:
    provider = "OPENAI_RESPONSES"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 180,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        definition = approved_provider(self.provider)
        assert definition.fixed_base_url is not None
        self._api_key = api_key
        self._base_url = definition.fixed_base_url.rstrip("/")
        self._models = definition.permitted_models
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def test_connection(self, exact_model_id: str) -> dict[str, object]:
        self._require_model(exact_model_id)
        response = self._client.get(
            f"{self._base_url}/models/{exact_model_id}", headers=self._headers()
        )
        if response.status_code >= 400:
            return {"healthy": False, "model": exact_model_id, "status_code": response.status_code}
        return {"healthy": True, "model": exact_model_id}

    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse:
        self._validate_request(request)
        body: dict[str, object] = {
            "model": request.exact_model_id,
            "store": False,
            "tools": [],
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Analyze only the supplied normalized market evidence. Your output is "
                        "advisory and cannot alter gates, rankings, assignments, or orders."
                    ),
                },
                {"role": "user", "content": json.dumps(request.evidence, sort_keys=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "market_advisory",
                    "strict": True,
                    "schema": advisory_json_schema(),
                }
            },
        }
        try:
            response = self._client.post(
                f"{self._base_url}/responses",
                headers=self._headers(),
                json=body,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException:
            return LlmAnalysisResponse("TIMED_OUT", None, reason="TIMED_OUT")
        except httpx.NetworkError:
            return LlmAnalysisResponse("FAILED", None, reason="TRANSIENT_PROVIDER_FAILURE")
        if response.status_code == 429:
            return LlmAnalysisResponse(
                "RATE_LIMITED",
                None,
                provider_request_id=response.headers.get("x-request-id"),
                retry_after_seconds=_retry_after(response),
                reason="RATE_LIMIT",
            )
        if response.status_code >= 400:
            return LlmAnalysisResponse(
                "FAILED",
                None,
                provider_request_id=response.headers.get("x-request-id"),
                reason=f"PROVIDER_HTTP_{response.status_code}",
            )
        payload = response.json()
        return LlmAnalysisResponse(
            "COMPLETED",
            _openai_analysis(payload),
            provider_request_id=str(payload.get("id") or response.headers.get("x-request-id") or ""),
            usage=_usage(payload.get("usage")),
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _require_model(self, model: str) -> None:
        if model not in self._models:
            raise ValueError("model is outside the reviewed OpenAI allowlist")

    def _validate_request(self, request: LlmAnalysisRequest) -> None:
        if request.provider != self.provider:
            raise ValueError("analysis request provider does not match this adapter")
        self._require_model(request.exact_model_id)
        if request.store:
            raise ValueError("market research analysis must not request provider storage")


def _openai_analysis(payload: dict[str, object]) -> dict[str, object] | None:
    direct = payload.get("output_parsed")
    if isinstance(direct, dict):
        return {str(key): value for key, value in direct.items()}
    text = payload.get("output_text")
    if isinstance(text, str):
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    parsed = json.loads(content["text"])
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
