from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from packages.shared.domain_types import AwareDateTime, utc_now


class AdapterStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class AdapterCapability(StrEnum):
    INSTRUMENT_DIRECTORY = "INSTRUMENT_DIRECTORY"
    DISCOVERY = "DISCOVERY"
    QUOTE = "QUOTE"
    TRADES = "TRADES"
    CANDLES = "CANDLES"
    ORDER_BOOK = "ORDER_BOOK"
    CONTRACT_DETAILS = "CONTRACT_DETAILS"
    FUTURES_CHAIN = "FUTURES_CHAIN"
    OPEN_INTEREST = "OPEN_INTEREST"
    FUNDING = "FUNDING"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    BROKER_TRADABILITY = "BROKER_TRADABILITY"


class AdapterError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AdapterCapabilityError(AdapterError):
    """Structured provider failure used by lane safe-failure handling."""

    def __init__(
        self,
        message: str,
        *,
        state: str = "UNAVAILABLE",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message, retryable=state in {"UNAVAILABLE", "STALE"})
        self.state = state
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ProviderObservation:
    observed_at: AwareDateTime
    max_age: timedelta

    @property
    def fresh(self) -> bool:
        return utc_now() - self.observed_at <= self.max_age


@dataclass(frozen=True)
class AdapterHealth:
    status: AdapterStatus
    checked_at: AwareDateTime
    last_success_at: datetime | None = None
    error: str | None = None
