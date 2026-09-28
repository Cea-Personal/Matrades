"""Account-scoped native broker terms required for an executable trade ticket."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.models import InstrumentSpecificationVersion
from packages.shared.domain_types import InstrumentType, QuantityUnit, round_down
from packages.shared.store import ResourceStore


@dataclass(frozen=True)
class LiveTradeTerms:
    account_currency: str
    price_currency: str
    quantity_unit: QuantityUnit
    contract_multiplier: Decimal
    tick_size: Decimal
    tick_value: Decimal | None
    quantity_minimum: Decimal
    quantity_maximum: Decimal
    quantity_step: Decimal
    specification_version_id: UUID

    def maximum_stepped_size(self) -> Decimal:
        size = round_down(self.quantity_maximum, self.quantity_step)
        self.validate_size(size)
        return size

    def validate_size(self, size: Decimal) -> None:
        if size < self.quantity_minimum or size > self.quantity_maximum:
            raise ValueError("approved volume is outside broker minimum/maximum")
        if size % self.quantity_step != 0:
            raise ValueError("approved volume does not match broker lot step")


async def load_live_trade_terms(
    db: AsyncSession,
    owner_id: UUID,
    account_id: UUID,
    venue_instrument_id: UUID,
    specification_version_id: UUID,
    instrument_type: InstrumentType,
) -> LiveTradeTerms:
    """Reject analytical proxy terms and unverified currency conversions."""
    store = ResourceStore(db)
    account = await store.get("account", account_id, owner_id)
    if account is None or account.state != "ACTIVE":
        raise ValueError("active trading account is required")
    account_currency = str(account.data.get("currency") or "").upper()
    if len(account_currency) != 3 or not account_currency.isalpha():
        raise ValueError("verified three-letter account currency is required")
    for record in await store.list("typed_instrument", owner_id):
        if record.state == "DELETED" or record.data.get("account_id") != str(account_id):
            continue
        if record.data.get("specification_version_id") != str(specification_version_id):
            continue
        raw = record.data.get("specification")
        listing = record.data.get("listing") or {}
        if not isinstance(raw, dict):
            continue
        specification = InstrumentSpecificationVersion.model_validate(raw)
        if (
            specification.venue_instrument_id != venue_instrument_id
            or specification.quantity_unit != record.data.get("quantity_unit")
            or listing.get("executable") is not True
            or specification.freshness != "VALID"
        ):
            raise ValueError("current executable broker specification is required")
        if instrument_type is InstrumentType.CFD and (
            specification.provenance.get("execution_authority") != "MT5_BROKER"
        ):
            raise ValueError(
                "broker-native CFD terms are required; research proxies cannot size trades"
            )
        if specification.price_currency.upper() != account_currency:
            raise ValueError(
                "verified account-currency conversion is unavailable for this instrument"
            )
        if specification.quantity_maximum is None:
            raise ValueError("broker maximum volume is required")
        if specification.quantity_maximum < specification.quantity_minimum:
            raise ValueError("invalid broker volume bounds")
        return LiveTradeTerms(
            account_currency=account_currency,
            price_currency=specification.price_currency.upper(),
            quantity_unit=specification.quantity_unit,
            contract_multiplier=specification.contract_multiplier,
            tick_size=specification.tick_size,
            tick_value=specification.tick_value,
            quantity_minimum=specification.quantity_minimum,
            quantity_maximum=specification.quantity_maximum,
            quantity_step=specification.quantity_step,
            specification_version_id=specification.id,
        )
    raise ValueError("current account-scoped broker specification is required")
