from datetime import UTC, datetime, timedelta

import pytest

from modules.research.features import IneligibleResearchEvidence, typed_fingerprint
from modules.research.sessions import weekend_close
from packages.shared.domain_types import AssetClass
from tests.unit.test_research_scoring import snapshot

SATURDAY = datetime(2026, 9, 26, 11, tzinfo=UTC)
FRIDAY_CLOSE = datetime(2026, 9, 25, 21, tzinfo=UTC)


def test_forex_last_session_history_is_valid_for_weekend_research():
    result, _, evidence = typed_fingerprint(
        snapshot(
            observed_at=SATURDAY,
            quote_observed_at=FRIDAY_CLOSE,
            candle_observed_at=FRIDAY_CLOSE - timedelta(hours=1),
        ),
        now=SATURDAY,
    )
    assert result.market_session == "WEEKEND_CLOSED"
    assert any("MARKET_CLOSED" in text for text in evidence)


@pytest.mark.parametrize(
    "field,reason",
    [
        ("quote_observed_at", "STALE_QUOTE"),
        ("candle_observed_at", "STALE_CANDLES"),
    ],
)
def test_weekend_exception_does_not_allow_old_session_data(field, reason):
    values = dict(
        observed_at=SATURDAY, quote_observed_at=FRIDAY_CLOSE, candle_observed_at=FRIDAY_CLOSE
    )
    values[field] = FRIDAY_CLOSE - timedelta(days=1)
    with pytest.raises(IneligibleResearchEvidence, match=reason):
        typed_fingerprint(snapshot(**values), now=SATURDAY)


@pytest.mark.parametrize(
    "field,reason",
    [
        ("quote_observed_at", "FUTURE_QUOTE_TIMESTAMP"),
        ("candle_observed_at", "FUTURE_CANDLE_TIMESTAMP"),
    ],
)
def test_future_timestamps_remain_invalid(field, reason):
    values = dict(observed_at=SATURDAY, quote_observed_at=SATURDAY, candle_observed_at=SATURDAY)
    values[field] = SATURDAY + timedelta(minutes=10)
    with pytest.raises(IneligibleResearchEvidence, match=reason):
        typed_fingerprint(snapshot(**values), now=SATURDAY)


def test_crypto_does_not_get_weekend_exception_and_fx_reopening_removes_it():
    assert weekend_close(AssetClass.CRYPTOCURRENCY, SATURDAY) is None
    assert weekend_close(AssetClass.FOREX, datetime(2026, 9, 27, 22, tzinfo=UTC)) is None
    value = snapshot(observed_at=SATURDAY, quote_observed_at=FRIDAY_CLOSE)
    value.listing.asset_class = AssetClass.CRYPTOCURRENCY
    with pytest.raises(IneligibleResearchEvidence, match="STALE_QUOTE"):
        typed_fingerprint(value, now=SATURDAY)


def test_weekend_close_tracks_new_york_daylight_saving():
    assert weekend_close(AssetClass.FOREX, SATURDAY) == FRIDAY_CLOSE
    assert weekend_close(AssetClass.FOREX, datetime(2026, 12, 12, 11, tzinfo=UTC)) == datetime(
        2026, 12, 11, 22, tzinfo=UTC
    )
