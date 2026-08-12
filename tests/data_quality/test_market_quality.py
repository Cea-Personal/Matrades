from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.market_data.ingestion import CanonicalBar
from traderx.market_data.quality import assess_bars
from traderx.shared.types import DataQuality


def test_negative_spread_and_stale_observations_are_quarantined() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    quality = assess_bars(
        [
            CanonicalBar(
                now - timedelta(days=1),
                Decimal("1"),
                Decimal("2"),
                Decimal("1"),
                Decimal("2"),
                Decimal("1"),
                Decimal("-1"),
            )
        ],
        now=now,
        max_age=timedelta(minutes=5),
    )
    assert quality.quality == DataQuality.QUARANTINED
    assert {"NEGATIVE_SPREAD", "STALE_DATA"}.issubset(quality.reason_codes)
