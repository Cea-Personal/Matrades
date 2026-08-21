from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class ProviderErrorKind(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    RATE_LIMIT = "RATE_LIMIT"
    TRANSIENT = "TRANSIENT"
    PERMANENT_INPUT = "PERMANENT_INPUT"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"
    CONTRADICTORY = "CONTRADICTORY"
    UNKNOWN = "UNKNOWN"


class SourceSemantics(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    ACTUAL = "ACTUAL"
    BROKER_PROXY = "BROKER_PROXY"
    # A composite feed may be useful for a precise price/candle continuity gap,
    # but is never a venue order book or executed-volume authority.
    AGGREGATED_PROXY = "AGGREGATED_PROXY"
    # Development-only scraped material is inspectable, but it is never
    # eligibility or risk-gate evidence.
    SCRAPED_EXPERIMENTAL = "SCRAPED_EXPERIMENTAL"
    UNAVAILABLE = "UNAVAILABLE"


class MarketDataCapability(StrEnum):
    INSTRUMENTS = "INSTRUMENTS"
    QUOTES = "QUOTES"
    TRADES = "TRADES"
    CANDLES = "CANDLES"
    TRADED_VOLUME = "TRADED_VOLUME"
    OPEN_INTEREST = "OPEN_INTEREST"
    TOP_OF_BOOK = "TOP_OF_BOOK"
    ORDER_BOOK = "ORDER_BOOK"
    SETTLEMENT = "SETTLEMENT"


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    provider: str
    provider_symbol: str
    capability: str
    semantics: SourceSemantics
    observed_at: datetime | None
    received_at: datetime
    payload: dict[str, object]
    venue: str | None = None
    provider_event_id: str | None = None
    sequence: str | None = None
    revision: str | None = None
    complete: bool = True
    final: bool = True
    quality_flags: tuple[str, ...] = ()
    raw_reference: str | None = None


@dataclass(frozen=True, slots=True)
class LlmAnalysisRequest:
    provider: str
    exact_model_id: str
    prompt_template_version: str
    output_schema_version: str
    inference_policy_version: str
    evidence: dict[str, object]
    timeout_seconds: int = 180
    store: bool = False
    # The market researcher and strategy researcher use the same advisory-only
    # provider boundary, but their strictly validated outputs are different.
    # Keeping the schema on the request avoids a generic free-text model call.
    output_schema_name: str = "market_advisory"
    output_schema: dict[str, object] | None = None
    system_instruction: str | None = None
    user_instruction: str | None = None


@dataclass(frozen=True, slots=True)
class LlmAnalysisResponse:
    state: str
    analysis: dict[str, object] | None
    provider_request_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    retry_after_seconds: int | None = None
    reason: str | None = None


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
    def get_account_changes(self, account_ref: str, cursor: str) -> dict[str, object] | None:
        """Return a documented delta response, or None when the provider has no cursor protocol."""
        ...


class MarketDataPort(Protocol):
    def test_connection(self) -> dict[str, object]: ...
    def capabilities(self) -> dict[str, SourceSemantics]: ...
    def discover_instruments(self, category: str) -> list[dict[str, object]]: ...
    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]: ...
    def get_observations(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        cursor: str | None = None,
    ) -> list[ProviderObservation]: ...


class LlmAnalysisPort(Protocol):
    """Advisory-only analysis. Implementations expose no tools or financial authority."""

    def test_connection(self, exact_model_id: str | None = None) -> dict[str, object]: ...
    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse: ...


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
