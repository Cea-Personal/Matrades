from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.backtesting.engine import BacktestCandle
from modules.strategies.evidence import resolve_approved_candidate, split_research_history


def candidate(instrument: str, score: float, observed_at: datetime) -> dict:
    return {
        "instrument": instrument,
        "category": "FOREX",
        "score": score,
        "rank": 1,
        "fingerprint": {
            "instrument": instrument,
            "category": "FOREX",
            "observed_at": observed_at.isoformat(),
            "source": "TWELVE_DATA",
            "source_version": "quote-v1",
            "regime": "TRENDING",
            "trend_score": 0.8,
            "volatility_score": 0.4,
            "liquidity_score": 0.9,
            "spread_score": 0.8,
            "fundamental_score": 0.3,
            "sentiment_score": 0.2,
            "event_risk": 0.1,
            "positioning_score": 0.2,
            "correlation_risk": 0.1,
            "data_quality": 0.95,
        },
        "evidence": ["provider snapshot"],
    }


def test_resolves_only_a_fresh_candidate_from_the_approved_selection() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    selection = {"selected": {"FOREX": "EUR/USD"}, "action": "APPROVE"}
    run = {
        "account_id": "account-1",
        "candidates": [
            candidate("GBP/USD", 99, now - timedelta(hours=1)),
            candidate("EUR/USD", 88, now - timedelta(hours=2)),
        ],
    }

    result = resolve_approved_candidate(selection, run, now=now, max_age=timedelta(hours=24))
    assert result.instrument == "EUR/USD"
    assert result.score == 88
    assert result.account_id == "account-1"


def test_replaced_instrument_without_a_fingerprint_fails_closed() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    selection = {"selected": {"FOREX": "USD/CHF"}, "action": "REPLACE"}
    run = {"account_id": "account-1", "candidates": [candidate("EUR/USD", 88, now)]}
    with pytest.raises(ValueError, match="approved candidate evidence"):
        resolve_approved_candidate(selection, run, now=now, max_age=timedelta(hours=24))


def test_stale_market_fingerprint_fails_closed() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    selection = {"selected": {"FOREX": "EUR/USD"}, "action": "APPROVE"}
    run = {
        "account_id": "account-1",
        "candidates": [candidate("EUR/USD", 88, now - timedelta(hours=25))],
    }
    with pytest.raises(ValueError, match="stale"):
        resolve_approved_candidate(selection, run, now=now, max_age=timedelta(hours=24))


def test_discovery_and_unseen_holdout_are_chronological_and_non_overlapping() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    candles = [
        BacktestCandle(
            observed_at=start + timedelta(hours=4 * index),
            open=Decimal(100 + index),
            high=Decimal(101 + index),
            low=Decimal(99 + index),
            close=Decimal("100.5") + index,
            volume=Decimal(1000),
        )
        for index in range(30)
    ]
    discovery, holdout = split_research_history(candles, discovery_ratio=Decimal("0.70"))
    assert len(discovery) == 21
    assert len(holdout) == 9
    assert discovery[-1].observed_at < holdout[0].observed_at
    assert not set(item.observed_at for item in discovery) & set(
        item.observed_at for item in holdout
    )
