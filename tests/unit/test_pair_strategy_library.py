from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.backtesting.engine import BacktestCandle, BacktestConfiguration, PointInTimeBacktester
from modules.backtesting.robustness import return_statistics
from modules.strategies.compiler import compile_strategy
from modules.strategies.family_library import cfd_family_hypotheses
from modules.strategies.monitoring import validation_passed
from modules.strategies.pair_profile import news_features, news_state, profile_pair, regime_matches
from modules.strategies.performance import FORMAL_GATES, rolling_health, select_strategy
from modules.strategies.signals import candle_features
from modules.strategies.trade_setup import build_strategy_setup
from tests.unit.test_strategy_trade_setup import strategy


def history(count=150):
    start = datetime(2026, 9, 21, tzinfo=UTC)
    return [
        BacktestCandle(
            observed_at=start + timedelta(minutes=i),
            open=100 + i,
            high=103 + i,
            low=Decimal("99.9") + i,
            close=101 + i,
            volume=100,
        )
        for i in range(count)
    ]


def test_profile_and_features_do_not_see_future_candles():
    values = history()
    before = candle_features(values, 40)
    values[-1] = values[-1].model_copy(update={"close": Decimal(5000), "high": Decimal(6000)})
    assert candle_features(values, 40) == before
    assert profile_pair(values, "XAUUSD", as_of=values[40].observed_at) == profile_pair(
        values[:41], "XAUUSD"
    )
    profile = profile_pair(values[:41], "XAUUSD")
    assert profile["regime"]["behaviour"] == "TRENDING"
    assert profile["regime"]["news"] == "UNKNOWN"
    assert profile["liquidity"]["status"] == "PROXY_ONLY"


def test_multi_axis_regime_rules_are_and_with_or_alternatives():
    features = candle_features(history(), 40)
    assert regime_matches(["TRENDING:BULLISH:NORMAL_VOLATILITY"], features)
    assert not regime_matches(["TRENDING:BEARISH"], features)
    assert regime_matches(["RANGING", "TRENDING"], features)
    assert not regime_matches(["UNCLASSIFIED"], features)
    assert not regime_matches(["TRENDING"], candle_features(history(10), 9))


def test_setup_and_backtest_both_enforce_regimes():
    values = history()
    spec = strategy(regimes=["RANGING"])
    result = PointInTimeBacktester().run(spec, values, BacktestConfiguration(initial_equity=10000))
    assert result.trade_count == 0
    signal = build_strategy_setup(
        spec, values, now=values[-1].observed_at + timedelta(minutes=1), timeframe_seconds=60
    )
    assert signal["status"] == "WAIT"
    assert signal["entry"] is None
    compiled = compile_strategy(spec)
    features = candle_features(values, len(values) - 1)
    assert not compiled.evaluate(features)
    generated = {}
    exec(compiled.generated_code, generated)  # noqa: S102 - exercise locally generated evaluator
    assert not generated["signal"](features)


def test_cfd_library_covers_all_seven_families_both_directions():
    spec = strategy(
        instrument_type="CFD", venue_instrument_id="listing", specification_version_id="spec"
    )
    hypotheses = cfd_family_hypotheses(spec, "history:cut")
    assert len(hypotheses) == 14
    assert {h.specification.family.value for h in hypotheses} == {
        "TREND",
        "MOMENTUM",
        "BREAKOUT",
        "PULLBACK",
        "MEAN_REVERSION",
        "RANGE",
        "LIQUIDITY_SWEEP",
    }
    assert all(
        h.specification.venue_instrument_id == "listing" and h.evidence_refs == ["history:cut"]
        for h in hypotheses
    )
    assert cfd_family_hypotheses(strategy(), "history:cut") == []


def test_robustness_requires_unseen_post_selection_candles():
    values = history()
    engine, config = (
        PointInTimeBacktester(),
        BacktestConfiguration(initial_equity=10000, spread="0.01", slippage="0.01"),
    )
    result = engine.run(strategy(), values, config, validation_start_after=values[-1].observed_at)
    assert not result.gates["out_of_sample"]
    assert not result.gates["walk_forward"]
    assert result.robustness["holdout_start_at"] is None
    result = engine.run(strategy(), values, config, validation_start_after=values[50].observed_at)
    assert result.robustness["out_of_sample"]["trade_count"] > 0
    assert len(result.robustness["walk_forward"]) == 3
    assert len(result.robustness["parameter_sensitivity"]) == 2
    assert result.robustness["independent_of_research_selection"]
    assert "sharpe_per_trade" in result.metrics
    assert result.regime_performance
    assert all("r" in trade and "risk" in trade for trade in result.attribution)


def test_missing_calendar_blocks_historical_event_restricted_entries():
    result = PointInTimeBacktester().run(
        strategy(event_rules=["block_high_impact_events"]),
        history(),
        BacktestConfiguration(initial_equity=10000),
    )
    assert result.trade_count == 0
    assert not result.gates["out_of_sample"]


def test_news_regime_distinguishes_coverage_and_before_after():
    now = datetime(2026, 9, 21, 12, tzinfo=UTC)
    assert news_state("XAUUSD", now, None) == "UNKNOWN"
    assert news_state("XAUUSD", now, []) == "NORMAL"
    assert (
        news_state(
            "XAUUSD",
            now,
            [
                {
                    "currency": "USD",
                    "impact": "HIGH",
                    "scheduled_at": (now + timedelta(minutes=10)).isoformat(),
                }
            ],
        )
        == "PRE_NEWS"
    )
    assert (
        news_state(
            "XAUUSD",
            now,
            [
                {
                    "currency": "USD",
                    "impact": "HIGH",
                    "scheduled_at": (now - timedelta(minutes=10)).isoformat(),
                }
            ],
        )
        == "POST_NEWS"
    )


def test_news_rules_fail_closed_without_calendar_and_match_current_context():
    now = datetime(2026, 9, 21, 12, tzinfo=UTC)
    features = {**candle_features(history(), 40), **news_features("XAUUSD", now, [])}
    assert regime_matches(["TRENDING:NORMAL_NEWS"], features)
    assert not regime_matches(["TRENDING:PRE_NEWS"], features)
    assert not regime_matches(["NORMAL_NEWS"], {**features, **news_features("XAUUSD", now, None)})
    spec = strategy(regimes=["TRENDING:NORMAL_NEWS"])
    config = BacktestConfiguration(initial_equity=10000)
    assert PointInTimeBacktester().run(spec, history(), config).trade_count == 0
    assert PointInTimeBacktester().run(spec, history(), config, calendar=[]).trade_count > 0
    negative_news = strategy(entry=[{"feature": "news_regime", "operator": "<", "value": "0"}])
    assert PointInTimeBacktester().run(negative_news, history(), config).trade_count == 0


def test_undefined_ratios_are_not_reported_as_zero():
    stats = return_statistics([1, 1, 1])
    assert stats["sharpe_per_trade"] is None
    assert stats["sortino_per_trade"] is None
    assert stats["profit_factor_r"] is None


def test_health_warms_up_then_suspends_a_losing_window():
    assert rolling_health([{"r": "-1"}] * 29)["status"] == "WARMUP"
    health = rolling_health([{"r": "-1"}] * 30)
    assert health["suspend"]
    assert health["windows"]["30"]["complete"]
    assert not health["windows"]["60"]["complete"]
    assert not rolling_health([{"r": "1"}] * 100)["suspend"]


SCOPE = {
    "account_id": "account",
    "instrument": "XAUUSD",
    "timeframe": "1h",
    "connection_id": "provider",
    "venue_instrument_id": "listing",
    "specification_version_id": "spec",
}
REGIME = "TRENDING:BULLISH:HIGH_VOLATILITY"


def candidate(version="v1", **changes):
    return {
        **SCOPE,
        "strategy_version_id": version,
        "state": "ACTIVE",
        "artifact_hash": "immutable",
        "performance_artifact_hash": "immutable",
        "validation_evidence": dict.fromkeys((*FORMAL_GATES, "paper", "paper_forward"), True),
        "regime_performance": {REGIME: {"trade_count": 10, "average_r": 1}},
        "health": {"suspend": False},
        "recent": {"trade_count": 10, "average_r": 0.5},
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"account_id": "other"},
        {"timeframe": "4h"},
        {"connection_id": "other"},
        {"state": "SUSPENDED"},
        {"performance_artifact_hash": "other"},
        {"health": {"suspend": True}},
        {"regime_performance": {}},
        {"recent": {"trade_count": 9, "average_r": 1}},
        {"validation_evidence": {}},
    ],
)
def test_selection_rejects_incompatible_or_weak_evidence(changes):
    assert select_strategy([candidate(**changes)], SCOPE, REGIME)["selected_version_id"] is None


def test_selection_compares_recent_performance_before_historical_score():
    better = candidate("v2", recent={"trade_count": 30, "average_r": 0.8})
    result = select_strategy([candidate(), better], SCOPE, REGIME)
    assert result["selected_version_id"] == "v2"
    assert not result["execution_authorized"]


def test_new_failed_robustness_gate_cannot_be_ignored_by_legacy_gates():
    evidence = dict.fromkeys(
        ("backtest", "out_of_sample", "walk_forward", "stress", "policy"), True
    )
    assert validation_passed(evidence)
    assert not validation_passed({**evidence, "cost_stress": False})
    assert not validation_passed({**evidence, "event_driven_execution": False})
    from modules.backtesting.promotion import promotable

    assert not promotable({**evidence, "paper": True, "event_driven_execution": False})
    assert (
        select_strategy(
            [
                candidate(
                    validation_evidence={
                        **candidate()["validation_evidence"],
                        "event_driven_execution": False,
                    }
                )
            ],
            SCOPE,
            REGIME,
        )["selected_version_id"]
        is None
    )
