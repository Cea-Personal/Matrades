from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx


class OandaEnvironment(StrEnum):
    PRACTICE = "PRACTICE"
    LIVE = "LIVE"


class OandaAdapterError(ValueError):
    """A response cannot safely be used for account truth."""


@dataclass(frozen=True, slots=True)
class OandaAccountCandidate:
    provider_account_id: str
    display_name: str
    currency: str
    account_mode: str


@dataclass(frozen=True, slots=True)
class OandaAccountSnapshot:
    provider_account_id: str
    balance: str
    equity: str
    equity_source: str
    realized_pl: str
    floating_pl: str
    margin_available: str | None
    open_position_count: int
    cursor: str
    observed_at: datetime
    raw: dict[str, object]


@dataclass(frozen=True, slots=True)
class OandaAccountChanges:
    cursor: str
    changes: dict[str, object]
    state: dict[str, object]
    observed_at: datetime


class OandaV20Adapter:
    """A deliberately small GET-only OANDA v20 account adapter.

    It does not expose an arbitrary method, URL, or raw HTTP client, so application code cannot
    turn a Personal Access Token into an order-capable client by accident.
    """

    _BASE_URLS = {
        OandaEnvironment.PRACTICE: "https://api-fxpractice.oanda.com",
        OandaEnvironment.LIVE: "https://api-fxtrade.oanda.com",
    }

    def __init__(
        self,
        *,
        personal_access_token: str,
        environment: OandaEnvironment,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not personal_access_token.strip():
            raise ValueError("an OANDA Personal Access Token is required")
        self._environment = environment
        self._now = now or (lambda: datetime.now(UTC))
        self._client = httpx.Client(
            base_url=self._BASE_URLS[environment],
            headers={"Authorization": f"Bearer {personal_access_token}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    @property
    def environment(self) -> OandaEnvironment:
        return self._environment

    def close(self) -> None:
        self._client.close()

    def discover_accounts(self) -> list[OandaAccountCandidate]:
        payload = self._get_json("/v3/accounts")
        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            raise OandaAdapterError("OANDA account discovery response is incomplete")
        candidates: list[OandaAccountCandidate] = []
        for account in accounts:
            if not isinstance(account, dict):
                raise OandaAdapterError("OANDA returned an invalid account candidate")
            account_id = self._required_string(account, "id")
            candidates.append(
                OandaAccountCandidate(
                    provider_account_id=account_id,
                    display_name=str(account.get("alias") or account_id),
                    currency=self._required_string(account, "currency"),
                    account_mode="PRACTICE" if self._environment == OandaEnvironment.PRACTICE else "LIVE",
                )
            )
        return candidates

    def bootstrap_account(self, account_id: str) -> OandaAccountSnapshot:
        account = self._account_payload(account_id)
        returned_id = self._required_string(account, "id")
        if returned_id != account_id:
            raise OandaAdapterError("OANDA returned data for a different selected account")
        return OandaAccountSnapshot(
            provider_account_id=account_id,
            balance=self._required_decimal_string(account, "balance"),
            equity=self._required_decimal_string(account, "NAV"),
            equity_source="NAV",
            realized_pl=str(account.get("pl", "0")),
            floating_pl=str(account.get("unrealizedPL", "0")),
            margin_available=self._optional_decimal_string(account, "marginAvailable"),
            open_position_count=self._required_int(account, "openPositionCount", default=0),
            cursor=self._required_string(account, "lastTransactionID"),
            observed_at=self._now(),
            raw=account,
        )

    def get_account_changes(self, account_id: str, cursor: str) -> OandaAccountChanges:
        if not cursor:
            raise ValueError("an accepted OANDA transaction cursor is required")
        payload = self._get_json(
            f"/v3/accounts/{account_id}/changes", params={"sinceTransactionID": cursor}
        )
        changes = payload.get("changes")
        state = payload.get("state")
        if not isinstance(changes, dict) or not isinstance(state, dict):
            raise OandaAdapterError("OANDA account changes response is incomplete")
        return OandaAccountChanges(
            cursor=self._required_string(payload, "lastTransactionID"),
            changes=changes,
            state=state,
            observed_at=self._now(),
        )

    def _account_payload(self, account_id: str) -> dict[str, object]:
        payload = self._get_json(f"/v3/accounts/{account_id}")
        account = payload.get("account")
        if not isinstance(account, dict):
            raise OandaAdapterError("OANDA account bootstrap response is incomplete")
        return account

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, object]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as error:
            raise OandaAdapterError("OANDA account read failed") from error
        if response.status_code >= 400:
            raise OandaAdapterError(f"OANDA account read failed with HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError as error:
            raise OandaAdapterError("OANDA returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise OandaAdapterError("OANDA returned an invalid response shape")
        return payload

    @staticmethod
    def _required_string(payload: dict[str, object], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise OandaAdapterError(f"OANDA response is missing {name}")
        return value

    @classmethod
    def _required_decimal_string(cls, payload: dict[str, object], name: str) -> str:
        return cls._required_string(payload, name)

    @staticmethod
    def _optional_decimal_string(payload: dict[str, object], name: str) -> str | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise OandaAdapterError(f"OANDA response has an invalid {name}")
        return value

    @staticmethod
    def _required_int(payload: dict[str, object], name: str, *, default: int) -> int:
        value = payload.get(name, default)
        if not isinstance(value, int) or value < 0:
            raise OandaAdapterError(f"OANDA response has an invalid {name}")
        return value
