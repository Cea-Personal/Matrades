"""Protocol boundaries for research data and logical agents."""

from __future__ import annotations

from typing import Any, Protocol

from modules.research.models import (
    MarketCategory,
    ResearchSnapshot,
    TypedResearchSnapshot,
)
from packages.shared.domain_types import ResearchLaneKey


class ResearchDataProvider(Protocol):
    async def gather(self, category: MarketCategory) -> list[ResearchSnapshot]: ...


class TypedResearchDataProvider(Protocol):
    async def gather_lane(self, lane: ResearchLaneKey) -> list[TypedResearchSnapshot]: ...


class ResearchAgentGateway(Protocol):
    async def invoke(
        self,
        logical_id: str,
        payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]: ...
