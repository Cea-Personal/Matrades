from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.market_data.ingestion import CanonicalBar
from traderx.market_data.quality import (
    DataPurpose,
    QualityPolicy,
    assess_bars,
    find_time_gaps,
    project_fail_closed_status,
)
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


def test_market_quality_detects_missing_intervals_without_forward_fill() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    bars = [
        CanonicalBar(
            now - timedelta(hours=3),
            Decimal("1"),
            Decimal("1.1"),
            Decimal("0.9"),
            Decimal("1"),
            Decimal("100"),
            Decimal("0.01"),
        ),
        CanonicalBar(
            now - timedelta(hours=1),
            Decimal("1"),
            Decimal("1.1"),
            Decimal("0.9"),
            Decimal("1"),
            Decimal("100"),
            Decimal("0.01"),
        ),
    ]
    gaps = find_time_gaps(bars, expected_interval=timedelta(hours=1))
    assert gaps == ((now - timedelta(hours=2), now - timedelta(hours=1)),)


def test_purpose_policy_quarantines_gaps_tick_alignment_and_excessive_spread() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    result = assess_bars(
        [
            CanonicalBar(
                now - timedelta(minutes=3),
                Decimal("1.001"),
                Decimal("1.011"),
                Decimal("0.991"),
                Decimal("1.001"),
                Decimal("10.5"),
                Decimal("0.02"),
            ),
            CanonicalBar(
                now - timedelta(minutes=1),
                Decimal("1.00"),
                Decimal("1.01"),
                Decimal("0.99"),
                Decimal("1.00"),
                Decimal("10"),
                Decimal("0.001"),
            ),
        ],
        now=now,
        policy=QualityPolicy(
            purpose=DataPurpose.OPPORTUNITY_MONITORING,
            max_age=timedelta(minutes=2),
            expected_interval=timedelta(minutes=1),
            maximum_gaps=0,
            maximum_spread=Decimal("0.01"),
            price_tick=Decimal("0.01"),
            volume_step=Decimal("1"),
        ),
    )
    assert result.quality == DataQuality.QUARANTINED
    assert set(result.reason_codes) == {
        "EXCESSIVE_GAPS",
        "EXCESSIVE_SPREAD",
        "PRICE_TICK_MISALIGNMENT",
        "VOLUME_STEP_MISALIGNMENT",
    }
    assert result.gap_count == 1
    assert project_fail_closed_status("ACTIVE", result) == "QUARANTINED"


def test_same_revision_with_different_values_is_contradictory() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    common = dict(
        observed_at=now - timedelta(minutes=1),
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("1"),
        volume=Decimal("10"),
        spread=Decimal("0.01"),
        revision=3,
    )
    result = assess_bars(
        [
            CanonicalBar(close=Decimal("1.5"), **common),
            CanonicalBar(close=Decimal("1.6"), **common),
        ],
        now=now,
        policy=QualityPolicy(
            purpose=DataPurpose.MARKET_SELECTION,
            max_age=timedelta(minutes=5),
            expected_interval=timedelta(minutes=1),
        ),
    )
    assert result.quality == DataQuality.CONTRADICTORY
    assert result.reason_codes == ("CONTRADICTORY_REVISION",)
