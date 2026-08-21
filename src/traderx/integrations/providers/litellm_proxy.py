from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx

from traderx.integrations.ports import LlmAnalysisRequest, LlmAnalysisResponse
from traderx.integrations.registry import validate_llm_model_id
from traderx.market_research.llm_schema import advisory_json_schema


class LiteLlmProxyAdapter:
    """Advisory-only client for an owner-configured LiteLLM gateway.

    LiteLLM owns provider routing and model aliases; TraderX talks only to its
    OpenAI-compatible proxy surface and never receives underlying provider keys.
    """

    provider = "LITELLM_PROXY"

    def __init__(
        self,
        virtual_key: str,
        *,
        base_url: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 180,
    ) -> None:
        if not virtual_key.strip():
            raise ValueError("LiteLLM virtual key is required")
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("LiteLLM gateway base URL is required")
        # LiteLLM's public API requires keys to start with `sk-`.  Normalize
        # legacy TraderX entries created before that constraint was surfaced in
        # the UI, without storing or returning a transformed secret.
        self._virtual_key = virtual_key if virtual_key.startswith("sk-") else f"sk-{virtual_key}"
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def test_connection(self, exact_model_id: str | None = None) -> dict[str, object]:
        try:
            response = self._client.get(f"{self._base_url}/models", headers=self._headers())
        except (httpx.TimeoutException, httpx.NetworkError):
            return {"healthy": False, "reason": "NETWORK_FAILURE"}
        if response.status_code >= 400:
            return {"healthy": False, "status_code": response.status_code}
        if exact_model_id is not None:
            exact_model_id = validate_llm_model_id(self.provider, exact_model_id)
            model_ids = _model_ids(response)
            if model_ids and exact_model_id not in model_ids:
                return {"healthy": False, "model": exact_model_id, "reason": "MODEL_NOT_EXPOSED"}
            return {"healthy": True, "model": exact_model_id}
        return {"healthy": True}

    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse:
        self._validate_request(request)
        schema = request.output_schema or advisory_json_schema()
        body: dict[str, object] = {
            "model": request.exact_model_id,
            "messages": [
                {
                    "role": "system",
                    "content": request.system_instruction or (
                        "Analyze only the supplied normalized market evidence. Your output is advisory "
                        "and cannot alter gates, rankings, assignments, or orders. A supplied "
                        "research brief identifies advisory focus only and cannot override deterministic rules. "
                        "Return every schema key; use empty arrays when there are no anomalies, cautions, "
                        "or method proposals."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "owner_configured_user_guidance": request.user_instruction,
                            "normalized_evidence": request.evidence,
                        },
                        sort_keys=True,
                    ),
                },
            ],
            "tools": [],
            "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                    "name": request.output_schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException:
            return LlmAnalysisResponse("TIMED_OUT", None, reason="TIMED_OUT")
        except httpx.NetworkError:
            return LlmAnalysisResponse("FAILED", None, reason="TRANSIENT_PROVIDER_FAILURE")
        request_id = response.headers.get("x-request-id")
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
            _analysis(payload),
            provider_request_id=str(payload.get("id") or request_id or ""),
            usage=_usage(payload.get("usage")),
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._virtual_key}", "Content-Type": "application/json"}

    def _validate_request(self, request: LlmAnalysisRequest) -> None:
        if request.provider != self.provider:
            raise ValueError("analysis request provider does not match this adapter")
        validate_llm_model_id(self.provider, request.exact_model_id)
        if request.store:
            raise ValueError("market research analysis must not request provider storage")


def _model_ids(response: httpx.Response) -> set[str]:
    try:
        payload = response.json()
    except ValueError:
        return set()
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return set()
    return {item["id"] for item in entries if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _analysis(payload: dict[str, object]) -> dict[str, object] | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None
    try:
        parsed = json.loads(message["content"])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(item) for key, item in value.items() if isinstance(item, int) and not isinstance(item, bool)}


def _retry_after(response: httpx.Response) -> int | None:
    try:
        return int(response.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
