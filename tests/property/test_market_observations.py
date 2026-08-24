from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from modules.market_data.ingestion import normalize
from modules.market_data.models import MarketObservation


def test_future_data_is_rejected():
    now = datetime.now(UTC)
    item = MarketObservation(
        instrument_id=uuid4(),
        source="fixture",
        source_symbol="EURUSD",
        observed_at=now + timedelta(seconds=1),
        received_at=now,
        bid=Decimal("1"),
        ask=Decimal("1.1"),
        provenance={"fixture": "1"},
    )
    with pytest.raises(ValueError):
        normalize(item)
