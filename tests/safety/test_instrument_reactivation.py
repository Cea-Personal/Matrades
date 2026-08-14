from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from traderx.instruments.reactivation import (
    AliasWindow,
    CoverageWindow,
    missing_intervals,
    plan_incremental_refresh,
)
from traderx.instruments.reactivation_service import begin_reactivation
from traderx.strategies.staleness import EvidenceFreshness, classify_evidence


def test_gap_detection_requires_revalidation_not_auto_reactivation() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    assert missing_intervals([], required_start=now - timedelta(days=1), required_end=now)
    assert (
        classify_evidence(validated_at=now - timedelta(days=1), now=now, data_gap=True).freshness
        == EvidenceFreshness.REVALIDATION_REQUIRED
    )


def test_alias_continuity_supports_incremental_gap_only_refresh() -> None:
    instrument_id = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    renamed = start + timedelta(days=5)
    end = start + timedelta(days=10)
    plan = plan_incremental_refresh(
        instrument_id=instrument_id,
        provider="MT5",
        aliases=[
            AliasWindow(instrument_id, "MT5", "EURUSD.a", start, renamed),
            AliasWindow(instrument_id, "MT5", "EURUSD", renamed, None),
        ],
        coverage=[
            CoverageWindow(start, start + timedelta(days=4), "MT5", "EURUSD.a"),
            CoverageWindow(renamed, end, "MT5", "EURUSD"),
        ],
        required_start=start,
        required_end=end,
    )
    assert [(gap.start, gap.end) for gap in plan.missing] == [
        (start + timedelta(days=4), renamed)
    ]


def test_alias_gap_and_ambiguous_overlap_fail_closed() -> None:
    instrument_id = uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=10)
    with pytest.raises(ValueError, match="uncovered"):
        plan_incremental_refresh(
            instrument_id=instrument_id,
            provider="MT5",
            aliases=[AliasWindow(instrument_id, "MT5", "EURUSD", start + timedelta(days=1))],
            coverage=[],
            required_start=start,
            required_end=end,
        )
    with pytest.raises(ValueError, match="ambiguous"):
        plan_incremental_refresh(
            instrument_id=instrument_id,
            provider="MT5",
            aliases=[
                AliasWindow(instrument_id, "MT5", "EURUSD", start, end),
                AliasWindow(instrument_id, "MT5", "EURUSD.a", start + timedelta(days=1), end),
            ],
            coverage=[],
            required_start=start,
            required_end=end,
        )


@pytest.mark.parametrize(
    ("age_days", "gap", "expected"),
    [
        (1, False, EvidenceFreshness.CURRENT),
        (1, True, EvidenceFreshness.REVALIDATION_REQUIRED),
        (100, False, EvidenceFreshness.REVALIDATION_REQUIRED),
        (200, False, EvidenceFreshness.STALE),
        (365, False, EvidenceFreshness.LEGACY),
    ],
)
def test_all_staleness_classes_end_in_review(
    age_days: int, gap: bool, expected: EvidenceFreshness
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    plan = classify_evidence(
        validated_at=now - timedelta(days=age_days), now=now, data_gap=gap
    )
    assert plan.freshness == expected
    outcome = begin_reactivation(plan)
    assert outcome.state != "ACTIVE"
    assert outcome.automatically_activated is False
