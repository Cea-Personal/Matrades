"""Canonical typed instrument registry used by research, risk, and reconciliation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.market_data.models import (
    InstrumentSpecificationVersion,
    UnderlyingAsset,
    VenueInstrument,
)
from packages.shared.domain_types import InstrumentType


class InstrumentRegistry:
    """Small provider-neutral registry; persistence adapters can replace its storage."""

    def __init__(self) -> None:
        self.underlyings: dict[UUID, UnderlyingAsset] = {}
        self.listings: dict[UUID, VenueInstrument] = {}
        self.specifications: dict[UUID, list[InstrumentSpecificationVersion]] = {}

    def register_underlying(self, asset: UnderlyingAsset) -> UnderlyingAsset:
        self.underlyings[asset.id] = asset
        return asset

    def register_listing(self, listing: VenueInstrument) -> VenueInstrument:
        if listing.instrument_type is InstrumentType.FUTURES and listing.continuous_analytical:
            listing = listing.model_copy(update={"executable": False})
        if listing.underlying_id not in self.underlyings:
            raise ValueError("venue listing references an unknown underlying")
        self.listings[listing.id] = listing
        return listing

    def register_specification(
        self, specification: InstrumentSpecificationVersion
    ) -> InstrumentSpecificationVersion:
        if specification.venue_instrument_id not in self.listings:
            raise ValueError("specification references an unknown venue listing")
        versions = self.specifications.setdefault(specification.venue_instrument_id, [])
        if any(item.version == specification.version for item in versions):
            raise ValueError("specification version already exists")
        versions.append(specification)
        versions.sort(key=lambda item: (item.effective_from, item.version))
        return specification

    def listing(self, listing_id: UUID) -> VenueInstrument:
        try:
            return self.listings[listing_id]
        except KeyError as exc:
            raise ValueError("unknown venue listing") from exc

    def specification_at(
        self, listing_id: UUID, as_of: datetime, *, require_fresh: bool = True
    ) -> InstrumentSpecificationVersion:
        self.listing(listing_id)
        versions = self.specifications.get(listing_id, [])
        matches = [
            item
            for item in versions
            if item.effective_from <= as_of
            and (item.effective_to is None or as_of < item.effective_to)
        ]
        if not matches:
            raise ValueError("no effective instrument specification")
        selected = matches[-1]
        if require_fresh and selected.freshness != "VALID":
            raise ValueError("instrument specification is stale or invalid")
        return selected

    def require_executable(self, listing_id: UUID, as_of: datetime) -> VenueInstrument:
        listing = self.listing(listing_id)
        if not listing.executable or listing.continuous_analytical:
            raise ValueError("continuous or non-executable listing cannot be traded")
        self.specification_at(listing_id, as_of)
        return listing
