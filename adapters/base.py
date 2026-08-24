from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from packages.shared.domain_types import AwareDateTime, utc_now


class AdapterStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class AdapterError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


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
