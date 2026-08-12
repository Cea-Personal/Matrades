from datetime import UTC, datetime, timedelta

from traderx.instruments.reactivation import missing_intervals
from traderx.strategies.staleness import EvidenceFreshness, classify_evidence


def test_gap_detection_requires_revalidation_not_auto_reactivation() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    assert missing_intervals([], required_start=now - timedelta(days=1), required_end=now)
    assert (
        classify_evidence(validated_at=now - timedelta(days=1), now=now, data_gap=True).freshness
        == EvidenceFreshness.REVALIDATION_REQUIRED
    )
