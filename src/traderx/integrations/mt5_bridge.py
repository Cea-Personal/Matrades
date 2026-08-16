from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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


def normalize_native_market_evidence(
    instruments: list[dict[str, object]], *, received_at: datetime
) -> list[dict[str, object]]:
    """Validate broker-specific market evidence received from the native outbound EA."""

    normalized: list[dict[str, object]] = []
    received = _utc(received_at)
    for raw in instruments:
        symbol = str(raw.get("symbol", "")).strip()
        if not symbol:
            raise Mt5BridgeError("MT5 instrument evidence is missing its symbol")
        record = dict(raw)
        record["source_semantics"] = "BROKER_PROXY"
        record["observed_at"] = _source_time(raw.get("observed_at"), fallback=received).isoformat()
        _validate_numeric(record, "bid", optional=True)
        _validate_numeric(record, "ask", optional=True)
        for series_name in ("closes", "tick_volumes", "real_volume", "bars_h1", "bars_d1"):
            value = record.get(series_name)
            if value is not None and not isinstance(value, list):
                raise Mt5BridgeError(f"MT5 instrument evidence has invalid {series_name}")
        real_volume = record.get("real_volume")
        record["real_volume_status"] = (
            "AVAILABLE" if isinstance(real_volume, list) and len(real_volume) > 0 else "UNAVAILABLE"
        )
        depth_status = str(record.get("depth_status", "UNAVAILABLE")).upper()
        if depth_status not in {"AVAILABLE", "UNAVAILABLE", "UNSUPPORTED"}:
            raise Mt5BridgeError("MT5 instrument evidence has invalid depth_status")
        depth = record.get("depth")
        if depth_status == "AVAILABLE" and (not isinstance(depth, list) or not depth):
            raise Mt5BridgeError("MT5 available depth evidence must contain book entries")
        if depth_status != "AVAILABLE":
            record["depth"] = None
        record["depth_status"] = depth_status
        record["capability_status"] = {
            "BROKER_SUPPORT": "AVAILABLE",
            "QUOTES": "AVAILABLE" if record.get("bid") is not None and record.get("ask") is not None else "UNAVAILABLE",
            "TICK_ACTIVITY": "AVAILABLE" if record.get("tick_volumes") else "UNAVAILABLE",
            "REAL_VOLUME": record["real_volume_status"],
            "ORDER_BOOK": depth_status,
        }
        normalized.append(record)
    return normalized


def _validate_numeric(payload: dict[str, object], field: str, *, optional: bool) -> None:
    value = payload.get(field)
    if value is None and optional:
        return
    try:
        Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise Mt5BridgeError(f"MT5 instrument evidence has invalid {field}") from error


def _source_time(value: object, *, fallback: datetime) -> datetime:
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        return _utc(value)
    text = str(value)
    try:
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=UTC)
        return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except (ValueError, OSError) as error:
        raise Mt5BridgeError("MT5 instrument evidence has invalid observed_at") from error


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise Mt5BridgeError("MT5 evidence times must be timezone-aware")
    return value.astimezone(UTC)
