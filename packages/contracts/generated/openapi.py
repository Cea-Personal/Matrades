"""Generated boundary models for the V2 autonomous execution endpoints.

Source: specs/001-matrades-product-platform/contracts/openapi.yaml
"""
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

CONTRACT_VERSION = "matrades.openapi.v2"


class AssetClass(StrEnum):
    FOREX = "FOREX"
    METALS = "METALS"
    CRYPTOCURRENCY = "CRYPTOCURRENCY"
    STOCKS = "STOCKS"


class InstrumentType(StrEnum):
    SPOT = "SPOT"
    CFD = "CFD"
    FUTURES = "FUTURES"


class QuantityUnit(StrEnum):
    UNITS = "UNITS"
    SHARES = "SHARES"
    LOTS = "LOTS"
    CONTRACTS = "CONTRACTS"


class ResearchLaneKey(BaseModel):
    asset_class: AssetClass
    instrument_type: InstrumentType


class InstrumentReference(BaseModel):
    venue_instrument_id: str
    specification_version_id: str
    futures_contract_id: str | None = None
    quantity_unit: QuantityUnit
    symbol: str
    executable: bool = True


class ResearchLaneResult(BaseModel):
    lane: ResearchLaneKey
    status: str
    candidate: InstrumentReference | None = None
    reason_code: str | None = None
    source_cut_refs: list[str] = Field(default_factory=list)


class RiskDecision(StrEnum):
    PASS = "PASS"  # noqa: S105 - risk decision label, not a credential
    REDUCE_SIZE = "REDUCE_SIZE"
    HARD_BLOCK = "HARD_BLOCK"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] = {}


class CandidateRisk(BaseModel):
    instrument: str
    direction: str
    requested_size: Decimal
    entry_price: Decimal
    stop_loss: Decimal
