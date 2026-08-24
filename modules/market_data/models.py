from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AwareDateTime


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
