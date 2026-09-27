from __future__ import annotations

from typing import Any

import httpx

from adapters.agent_runtime.result import RuntimeResult


class LiteLLMClient:
    """Alternative runtime used only after an explicit profile assignment."""

    runtime_type = "LITELLM_GATEWAY"

    def __init__(
        self, base_url: str, credential: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.client = client or httpx.AsyncClient(
            base_url=base_url, timeout=30, headers={"Authorization": f"Bearer {credential}"}
        )

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = payload.get("output_schema")
        request = {
            "model": payload.get("model"),
            "messages": [
                {"role": "system", "content": str(payload.get("system", ""))},
                {
                    "role": "user",
                    "content": (
                        f"{payload.get('user', '')}\n\n"
                        f"STRUCTURED INPUT:\n{payload.get('input', {})}"
                    ),
                },
            ],
            "temperature": 0,
        }
        if schema:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "matrades_agent_response", "schema": schema},
            }
        response = await self.client.post("/v1/chat/completions", json=request)
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if isinstance(content, str):
            import json

            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return self._result(parsed, data)
        if isinstance(content, dict):
            return self._result(content, data)
        raise ValueError("LiteLLM response did not contain a structured JSON object")

    @staticmethod
    def _result(content: dict[str, Any], data: dict[str, Any]) -> RuntimeResult:
        model = data.get("model")
        verified = isinstance(model, str) and bool(model.strip())
        return RuntimeResult(
            content,
            actual_model=model if verified else None,
            model_evidence_source="gateway_response" if verified else None,
        )

    async def models(self) -> list[dict[str, Any]]:
        response = await self.client.get("/v1/models")
        response.raise_for_status()
        return list(response.json().get("data", []))

    async def close(self) -> None:
        await self.client.aclose()
