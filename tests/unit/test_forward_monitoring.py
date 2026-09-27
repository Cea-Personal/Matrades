from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.api.app.routes.strategies import PaperEvidenceInput, PaperTradingInput
from modules.backtesting.engine import BacktestCandle, BacktestConfiguration
from modules.strategies.monitoring import ENGINE, observe, paper_gates
from tests.unit.test_strategy_trade_setup import strategy

BASE = datetime(2026, 9, 22, 0, tzinfo=UTC)
SPEC = strategy(asset_class="CRYPTOCURRENCY")
CONFIG = BacktestConfiguration(
    initial_equity=10000,
    spread="0.1",
    commission="0.1",
    slippage="0.01",
    max_daily_loss=500,
    max_total_loss=1000,
)


def bars(count):
    return [
        BacktestCandle(
            observed_at=BASE + timedelta(hours=i), open=100, high=101, low=99, close=100, volume=10
        )
        for i in range(count)
    ]


def tick(data, values, hour):
    return observe(
        SPEC,
        data,
        values,
        now=BASE + timedelta(hours=hour, seconds=1),
        timeframe_seconds=3600,
        configuration=CONFIG,
        paper=True,
    )


def test_warmup_does_not_create_historical_trades_or_consume_incomplete_candles():
    data = tick({"started_at": (BASE + timedelta(hours=6)).isoformat()}, bars(10), 6)
    assert len(data["candles"]) == 6
    assert data["trade_count"] == 0
    assert list(data["entry_intents"]) == [(BASE + timedelta(hours=6)).isoformat()]


def test_paper_records_real_forward_outcomes_once_and_keeps_open_positions():
    state = tick({"started_at": (BASE + timedelta(hours=6)).isoformat()}, bars(6), 6)
    opened = tick(state, bars(7), 7)
    assert opened["trade_count"] == 0
    assert len(opened["open_positions"]) == 1
    assert len(opened["entry_intents"]) == 1
    values = bars(8)
    values[-1] = values[-1].model_copy(update={"low": Decimal(95)})
    closed = tick(opened, values, 8)
    replayed = tick(closed, values, 8)
    assert closed["trade_count"] == replayed["trade_count"] == 1
    assert closed["trades"] == replayed["trades"]
    assert Decimal(closed["net_profit"]) < 0
    assert not closed["open_positions"]
    assert closed["execution_authorized"] is False


def test_late_observation_cannot_reconstruct_an_entry_after_the_outcome():
    state = observe(
        SPEC,
        {"started_at": BASE.isoformat()},
        bars(6),
        now=BASE + timedelta(hours=6, minutes=20),
        timeframe_seconds=3600,
        configuration=CONFIG,
        paper=True,
    )
    assert state["entry_intents"] == {}
    assert tick(state, bars(8), 8)["trade_count"] == 0


def test_forward_news_context_is_frozen_when_calendar_coverage_changes():
    spec = strategy(
        asset_class="CRYPTOCURRENCY",
        filters=[{"feature": "news_regime", "operator": "==", "value": "0"}],
    )
    state = observe(
        spec,
        {"started_at": (BASE + timedelta(hours=6)).isoformat()},
        bars(6),
        now=BASE + timedelta(hours=6, seconds=1),
        timeframe_seconds=3600,
        configuration=CONFIG,
        calendar=[],
        paper=True,
    )
    assert state["news_contexts"][(BASE + timedelta(hours=6)).isoformat()] == "NORMAL"
    values = bars(8)
    values[-1] = values[-1].model_copy(update={"low": Decimal(95)})
    closed = observe(
        spec,
        state,
        values,
        now=BASE + timedelta(hours=8, seconds=1),
        timeframe_seconds=3600,
        configuration=CONFIG,
        calendar=None,
        paper=True,
    )
    assert closed["trade_count"] == 1
    assert closed["trades"][0]["news_regime"] == "NORMAL"
    assert closed["latest_signal"]["status"] == "WAIT"


def test_candle_gap_prevents_paper_promotion():
    state = tick({"started_at": (BASE + timedelta(hours=6)).isoformat()}, bars(6), 6)
    state = tick(state, [*bars(6), bars(8)[-1]], 8)
    assert state["data_complete"] is False
    assert paper_gates(state)["data_complete"] is False


def test_paper_review_rejects_entered_metrics_and_backdated_sessions():
    with pytest.raises(ValidationError):
        PaperEvidenceInput(trade_count=100, net_profit="999", policy_passed=True)
    with pytest.raises(ValidationError):
        PaperTradingInput(observation_start=BASE, observation_end=BASE + timedelta(days=30))
    assert not paper_gates({"trade_count": 10, "net_profit": "10"})["forward_observation"]


def test_closed_market_and_missing_event_context_cannot_record_intents():
    spec = strategy(asset_class="FOREX", event_rules=["block_high_impact_events"])
    data = observe(
        spec,
        {"started_at": BASE.isoformat()},
        bars(6),
        now=BASE + timedelta(hours=6, seconds=1),
        timeframe_seconds=3600,
        configuration=CONFIG,
        paper=True,
    )
    assert data["latest_signal"]["status"] == "BLOCKED"
    assert data["entry_intents"] == {}


def test_stop_entries_preserves_monitoring_and_no_new_orders():
    state = tick(
        {
            "started_at": (BASE + timedelta(hours=6)).isoformat(),
            "entry_cutoff": (BASE + timedelta(hours=5)).isoformat(),
        },
        bars(6),
        6,
    )
    assert state["entry_intents"] == {}
    assert state["latest_signal"]["status"] == "WAIT"
    assert state["engine"] == ENGINE
