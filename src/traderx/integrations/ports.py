from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol


class BrokerReadPort(Protocol):
    """Read-only broker contract. Live order methods are intentionally absent."""

    def test_connection(self) -> None: ...
    def get_account_snapshot(self, account_ref: str) -> dict[str, object]: ...
    def list_instruments(self, account_ref: str) -> list[dict[str, object]]: ...
    def get_instrument_spec(self, account_ref: str, provider_symbol: str) -> dict[str, object]: ...
    def get_open_positions(self, account_ref: str) -> list[dict[str, object]]: ...
    def get_deals(
        self, account_ref: str, cursor_or_range: str | None
    ) -> list[dict[str, object]]: ...
    def get_account_changes(
        self, account_ref: str, cursor: str
    ) -> dict[str, object] | None:
        """Return a documented delta response, or None when the provider has no cursor protocol."""
        ...


class MarketDataPort(Protocol):
    def discover_instruments(self, category: str) -> list[dict[str, object]]: ...
    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]: ...


class NotificationPort(Protocol):
    def test_connection(self) -> None: ...
    def send(
        self, notification_id: str, recipient: str, content: str, idempotency_hint: str
    ) -> str: ...


class ArtifactPort(Protocol):
    def put_immutable(
        self, content: bytes, media_type: str, checksum: str, classification: str
    ) -> str: ...
    def verify(self, artifact_ref: str, checksum: str) -> bool: ...


class Clock(Protocol):
    def now_utc(self) -> datetime: ...


class PositionSizingPort(Protocol):
    def convert(self, amount: Decimal, source_currency: str, target_currency: str) -> Decimal: ...
