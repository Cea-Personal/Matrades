"""Effective-dated instrument-term authority and safe invalidation helpers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.market_data.instruments import InstrumentRegistry
from modules.market_data.models import InstrumentSpecificationVersion


class SpecificationAuthority:
    def __init__(self, registry: InstrumentRegistry) -> None:
        self.registry = registry

    def activate(self, specification: InstrumentSpecificationVersion) -> None:
        if specification.freshness != "VALID":
            raise ValueError("only a valid specification can be activated")
        self.registry.register_specification(specification)

    def require(self, listing_id: UUID, as_of: datetime) -> InstrumentSpecificationVersion:
        return self.registry.specification_at(listing_id, as_of, require_fresh=True)

    @staticmethod
    def invalidates_actionable(
        previous: InstrumentSpecificationVersion,
        current: InstrumentSpecificationVersion,
    ) -> bool:
        return previous.model_dump(exclude={"id", "version"}) != current.model_dump(
            exclude={"id", "version"}
        )
