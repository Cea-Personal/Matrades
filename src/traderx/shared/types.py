from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import StrEnum
from typing import NewType
from uuid import UUID, uuid4

EntityId = NewType("EntityId", UUID)


def new_id() -> EntityId:
    return EntityId(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, float):
        raise TypeError("binary floating point is forbidden at financial boundaries")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"invalid decimal: {value!r}") from error
    if not result.is_finite():
        raise ValueError("financial decimal must be finite")
    return result


def floor_to_step(value: Decimal | str | int, step: Decimal | str | int) -> Decimal:
    exact_value = as_decimal(value)
    exact_step = as_decimal(step)
    if exact_step <= 0:
        raise ValueError("step must be greater than zero")
    return (exact_value / exact_step).to_integral_value(rounding=ROUND_DOWN) * exact_step


class MarketCategory(StrEnum):
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"


class RiskState(StrEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DEFENSIVE = "DEFENSIVE"
    LOCKDOWN = "LOCKDOWN"


class RiskDecisionKind(StrEnum):
    PASS = "PASS"
    PASS_REDUCED = "PASS_REDUCED"
    BLOCKED = "BLOCKED"


class DataQuality(StrEnum):
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    CONTRADICTORY = "CONTRADICTORY"
    QUARANTINED = "QUARANTINED"
    UNKNOWN = "UNKNOWN"


class DomainError(Exception):
    code = "domain_error"
    status_code = 422

    def __init__(self, detail: str, *, fields: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.fields = fields or []


class AuthorizationError(DomainError):
    code = "authorization_denied"
    status_code = 403


class AuthenticationError(DomainError):
    code = "authentication_required"
    status_code = 401


class AuthenticationRateLimited(DomainError):
    code = "authentication_rate_limited"
    status_code = 429


class BootstrapUnavailable(DomainError):
    code = "bootstrap_unavailable"
    status_code = 409


class SafetyDependencyUnavailable(DomainError):
    code = "safety_dependency_unavailable"
    status_code = 503


class ConcurrentModification(DomainError):
    code = "concurrent_modification"
    status_code = 412


class InvalidTransition(DomainError):
    code = "invalid_transition"
    status_code = 409


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", as_decimal(self.amount))
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
