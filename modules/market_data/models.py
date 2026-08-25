from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from packages.shared.domain_types import (
    AssetClass,
    AwareDateTime,
    InstrumentType,
    LaneStatus,
    QuantityUnit,
    ResearchLaneKey,
)


class AssetCategory(StrEnum):
    FOREX = "FOREX"
    METAL = "METAL"
    CRYPTO = "CRYPTO"


class Instrument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    base: str
    quote: str
    category: AssetCategory
    aliases: set[str] = set()


class UnderlyingAsset(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    display_name: str
    asset_class: AssetClass
    base_currency: str | None = None
    quote_currency: str | None = None


class VenueInstrument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    underlying_id: UUID
    venue: str
    provider: str
    symbol: str
    asset_class: AssetClass
    instrument_type: InstrumentType
    futures_contract_id: UUID | None = None
    executable: bool = True
    continuous_analytical: bool = False
    aliases: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def lifecycle_consistency(self) -> VenueInstrument:
        if self.continuous_analytical and self.instrument_type is not InstrumentType.FUTURES:
            raise ValueError("only futures may use a continuous analytical series")
        if self.continuous_analytical and self.executable:
            raise ValueError("continuous analytical futures cannot be executable")
        if self.instrument_type is InstrumentType.FUTURES and not self.continuous_analytical:
            if self.futures_contract_id is None:
                raise ValueError("executable futures listing requires a dated contract reference")
        return self


class InstrumentSpecificationVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    venue_instrument_id: UUID
    version: int = Field(default=1, ge=1)
    effective_from: AwareDateTime
    effective_to: AwareDateTime | None = None
    price_currency: str
    settlement_currency: str | None = None
    quantity_unit: QuantityUnit
    contract_multiplier: Decimal = Decimal("1")
    tick_size: Decimal = Decimal("0.00001")
    tick_value: Decimal | None = None
    quantity_minimum: Decimal = Decimal("0.01")
    quantity_maximum: Decimal | None = None
    quantity_step: Decimal = Decimal("0.01")
    margin_terms: dict[str, str] = Field(default_factory=dict)
    financing_terms: dict[str, str] = Field(default_factory=dict)
    expiry: AwareDateTime | None = None
    first_notice: AwareDateTime | None = None
    last_trade: AwareDateTime | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    freshness: str = "VALID"

    @model_validator(mode="after")
    def valid_terms(self) -> InstrumentSpecificationVersion:
        if self.contract_multiplier <= 0 or self.tick_size <= 0:
            raise ValueError("contract multiplier and tick size must be positive")
        if self.quantity_minimum <= 0 or self.quantity_step <= 0:
            raise ValueError("quantity bounds must be positive")
        if not self.provenance:
            raise ValueError("instrument specification provenance is required")
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("specification effective_to must follow effective_from")
        return self


class FuturesSeries(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    underlying_id: UUID
    root_symbol: str
    venue: str
    continuous_for_analysis: bool = True


class FuturesContract(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    series_id: UUID
    venue_instrument_id: UUID
    contract_code: str
    listed_at: AwareDateTime
    first_notice: AwareDateTime | None = None
    last_trade: AwareDateTime
    settled_at: AwareDateTime | None = None
    status: str = "ACTIVE"


class FuturesChainSnapshot(BaseModel):
    series_id: UUID
    as_of: AwareDateTime
    source_cut_id: str
    contract_ids: tuple[UUID, ...]
    observed_at: AwareDateTime


class ContinuousFuture(BaseModel):
    series_id: UUID
    as_of: AwareDateTime
    source: str
    roll_rule: str
    executable: bool = False


class RollRule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    series_id: UUID
    name: str
    first_notice_buffer_days: int = Field(default=5, ge=0)
    last_trade_buffer_days: int = Field(default=2, ge=0)
    liquidity_field: str = "open_interest"


class CorporateAction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    underlying_id: UUID
    action_type: str
    effective_at: AwareDateTime
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    source: str
    source_version: str


class FinancingObservation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    venue_instrument_id: UUID
    effective_at: AwareDateTime
    financing_type: str
    rate_or_amount: Decimal
    currency: str
    source: str
    source_version: str


class ResearchLane(BaseModel):
    key: ResearchLaneKey
    status: LaneStatus = LaneStatus.NOT_CONFIGURED
    enabled: bool = True
    schedule: dict[str, str | bool | list[int]] = Field(default_factory=dict)


class MarketObservation(BaseModel):
    instrument_id: UUID
    source: str
    source_symbol: str
    observed_at: AwareDateTime
    received_at: AwareDateTime
    bid: Decimal | None = None
    ask: Decimal | None = None
    price: Decimal | None = None
    sequence: int | None = None
    provenance: dict[str, str] = {}
    venue_instrument_id: UUID | None = None
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    specification_version_id: UUID | None = None
    source_cut_id: str | None = None

    @model_validator(mode="after")
    def typed_observation_consistency(self) -> MarketObservation:
        if self.instrument_type is not None:
            if self.venue_instrument_id is None or self.specification_version_id is None:
                raise ValueError("typed observations require listing and specification references")
            if self.asset_class is None:
                raise ValueError("typed observations require an asset class")
        if self.instrument_type == InstrumentType.FUTURES and self.venue_instrument_id is None:
            raise ValueError("futures observations require an exact venue listing")
        return self
