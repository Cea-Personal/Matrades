from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class Mt5BridgeError(ValueError):
    """The MT5 bridge response cannot be trusted as account truth."""


@dataclass(frozen=True, slots=True)
class Mt5BridgeIdentity:
    bridge_url: str
    account_login: str
    server: str


@dataclass(frozen=True, slots=True)
class Mt5BridgeAccountSnapshot:
    balance: str
    equity: str
    currency: str
    positions: list[dict[str, object]]
    deals: list[dict[str, object]]
    instruments: list[dict[str, object]]
    terminal_version: str


class Mt5BridgeAdapter:
    """Narrow HTTPS client for the isolated MT5 read-only bridge.

    The caller supplies a transport configured for mTLS.  This adapter never exposes a general
    HTTP request method or an MT5 terminal client.
    """

    def __init__(
        self,
        *,
        identity: Mt5BridgeIdentity,
        bridge_client_secret: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not identity.bridge_url.startswith("https://"):
            raise ValueError("the MT5 bridge URL must use HTTPS")
        if not bridge_client_secret.strip():
            raise ValueError("an MT5 bridge client credential is required")
        self._identity = identity
        self._client = httpx.Client(
            base_url=identity.bridge_url,
            headers={
                "Authorization": f"Bearer {bridge_client_secret}",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def test_connection(self) -> None:
        health = self._get_json("/v1/health")
        self._verify_terminal_state(health)

    def get_account_snapshot(self, account_ref: str) -> Mt5BridgeAccountSnapshot:
        self._assert_account_ref(account_ref)
        payload = self._get_json("/v1/account-snapshot")
        self._verify_terminal_state(payload)
        return Mt5BridgeAccountSnapshot(
            balance=self._required_string(payload, "balance"),
            equity=self._required_string(payload, "equity"),
            currency=self._required_string(payload, "currency"),
            positions=self._required_records(payload, "positions"),
            deals=self._required_records(payload, "deals"),
            instruments=self._required_records(payload, "instruments"),
            terminal_version=self._required_string(payload, "terminal_version"),
        )

    def get_open_positions(self, account_ref: str) -> list[dict[str, object]]:
        self._assert_account_ref(account_ref)
        return self._required_records(self._get_json("/v1/positions"), "items", fallback_list=True)

    def get_deals(self, account_ref: str, cursor_or_range: str | None) -> list[dict[str, object]]:
        del cursor_or_range
        self._assert_account_ref(account_ref)
        return self._required_records(self._get_json("/v1/deals"), "items", fallback_list=True)

    def list_instruments(self, account_ref: str) -> list[dict[str, object]]:
        self._assert_account_ref(account_ref)
        return self._required_records(
            self._get_json("/v1/instruments"), "items", fallback_list=True
        )

    def get_instrument_spec(self, account_ref: str, provider_symbol: str) -> dict[str, object]:
        if not provider_symbol:
            raise ValueError("a provider symbol is required")
        for item in self.list_instruments(account_ref):
            if item.get("symbol") == provider_symbol:
                return item
        return self._not_found(provider_symbol)

    def get_account_changes(self, account_ref: str, cursor: str) -> None:
        del account_ref, cursor
        # MT5 has no documented transaction cursor. Reconciliation uses overlapping deal windows.
        return None

    def _get_json(self, path: str) -> dict[str, object]:
        try:
            response = self._client.get(path)
        except httpx.HTTPError as error:
            raise Mt5BridgeError("MT5 bridge read failed") from error
        if response.status_code >= 400:
            raise Mt5BridgeError(f"MT5 bridge read failed with HTTP {response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError as error:
            raise Mt5BridgeError("MT5 bridge returned invalid JSON") from error
        if isinstance(payload, list):
            return {"items": payload}
        if not isinstance(payload, dict):
            raise Mt5BridgeError("MT5 bridge returned an invalid response shape")
        return payload

    def _verify_terminal_state(self, payload: dict[str, object]) -> None:
        if payload.get("login") != self._identity.account_login:
            raise Mt5BridgeError("MT5 bridge returned a different account login")
        if payload.get("server") != self._identity.server:
            raise Mt5BridgeError("MT5 bridge returned a different broker server")
        if payload.get("trading_disabled") is not True:
            raise Mt5BridgeError("MT5 bridge did not prove that trading is disabled")

    def _assert_account_ref(self, account_ref: str) -> None:
        if account_ref != self._identity.account_login:
            raise Mt5BridgeError("MT5 account reference does not match the registered bridge")

    @staticmethod
    def _required_string(payload: dict[str, object], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise Mt5BridgeError(f"MT5 bridge response is missing {name}")
        return value

    @staticmethod
    def _required_records(
        payload: dict[str, object], name: str, *, fallback_list: bool = False
    ) -> list[dict[str, object]]:
        value = payload.get(name)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise Mt5BridgeError(f"MT5 bridge response has invalid {name}")
        return value

    @staticmethod
    def _not_found(provider_symbol: str) -> dict[str, object]:
        raise Mt5BridgeError(f"MT5 bridge did not return instrument {provider_symbol}")
