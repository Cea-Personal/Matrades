"""Point-in-time lifecycle fixtures for replay tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from modules.market_data.models import CorporateAction, FinancingObservation


def split(underlying_id: UUID) -> CorporateAction:
    return CorporateAction(
        underlying_id=underlying_id,
        action_type="SPLIT",
        effective_at=datetime(2026, 2, 1, tzinfo=UTC),
        ratio=Decimal("2"),
        source="fixture",
        source_version="1",
    )


def financing(venue_instrument_id: UUID) -> FinancingObservation:
    return FinancingObservation(
        venue_instrument_id=venue_instrument_id,
        effective_at=datetime(2026, 2, 1, tzinfo=UTC),
        financing_type="OVERNIGHT",
        rate_or_amount=Decimal("0.0001"),
        currency="USD",
        source="fixture",
        source_version="1",
    )
