from __future__ import annotations

from typing import Any

import httpx


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
        response = await self.client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()
