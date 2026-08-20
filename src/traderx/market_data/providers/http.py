from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from traderx.integrations.registry import approved_provider


@dataclass(frozen=True, slots=True)
class ProviderTransportError(RuntimeError):
    kind: str
    detail: str
    retry_after_seconds: int | None = None
    status_code: int | None = None

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


class ProviderHttpTransport:
    """Persistent GET-only transport bound to one reviewed provider endpoint."""

    def __init__(
        self,
        provider: str,
        *,
        credential: str | None = None,
        client: httpx.Client | None = None,
        maximum_attempts: int = 3,
        timeout_seconds: float = 30,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        definition = approved_provider(provider)
        if definition.fixed_base_url is None:
            raise ValueError("the reviewed provider has no fixed HTTP endpoint")
        if maximum_attempts < 1 or maximum_attempts > 3:
            raise ValueError("specialist provider attempts must be between one and three")
        self.provider = definition.provider
        self.base_url = definition.fixed_base_url.rstrip("/")
        self._credential = credential
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._maximum_attempts = maximum_attempts
        self._sleep = sleep
        self.last_response_hash: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object] | list[object]:
        if method.upper() != "GET":
            raise ValueError("reviewed market-data transport permits GET only")
        if not path.startswith("/") or "://" in path:
            raise ValueError("provider paths must be relative to the reviewed fixed endpoint")
        request_headers = {"Accept": "application/json", **(headers or {})}
        if self._credential:
            # Twelve Data documents its server-side API-key authorization scheme.
            # Other reviewed market-data adapters currently use bearer credentials.
            request_headers["Authorization"] = (
                f"apikey {self._credential}"
                if self.provider == "TWELVE_DATA"
                else f"Bearer {self._credential}"
            )
        last_error: ProviderTransportError | None = None
        for attempt in range(1, self._maximum_attempts + 1):
            try:
                response = self._client.request(
                    "GET",
                    f"{self.base_url}{path}",
                    params=params,
                    headers=request_headers,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_error = ProviderTransportError("TRANSIENT", "provider request failed")
                if attempt < self._maximum_attempts:
                    self._sleep(float(attempt))
                    continue
                raise last_error from error
            retry_after = _retry_after(response)
            if response.status_code == 429:
                last_error = ProviderTransportError(
                    "RATE_LIMIT",
                    "provider rate limit exhausted",
                    retry_after_seconds=retry_after,
                    status_code=429,
                )
                if attempt < self._maximum_attempts:
                    self._sleep(float(retry_after or attempt))
                    continue
                raise last_error
            if response.status_code in {401, 403}:
                kind = "AUTHENTICATION" if response.status_code == 401 else "AUTHORIZATION"
                raise ProviderTransportError(
                    kind,
                    "provider credential or entitlement was rejected",
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                last_error = ProviderTransportError(
                    "TRANSIENT", "provider service failed", status_code=response.status_code
                )
                if attempt < self._maximum_attempts:
                    self._sleep(float(attempt))
                    continue
                raise last_error
            if response.status_code >= 400:
                raise ProviderTransportError(
                    "PERMANENT_INPUT",
                    "provider rejected the reviewed request",
                    status_code=response.status_code,
                )
            try:
                payload: Any = response.json()
            except ValueError as error:
                raise ProviderTransportError("UNKNOWN", "provider returned invalid JSON") from error
            if not isinstance(payload, (dict, list)):
                raise ProviderTransportError("UNKNOWN", "provider returned an invalid response")
            self.last_response_hash = hashlib.sha256(response.content).hexdigest()
            return payload
        raise last_error or ProviderTransportError("UNKNOWN", "provider request failed")


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return max(0, parsed)
