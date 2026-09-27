import lzma
import struct
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from adapters.macro.providers import CftcProvider, positioning_features
from adapters.market_data.public_research import (
    ccxt_history,
    decode_ticks,
    dukascopy_history,
    ecb_series,
)
from modules.backtesting.engine import BacktestConfiguration
from modules.backtesting.vectorbt_research import parameter_sweep
from modules.connections.models import ConnectionProfile
from modules.connections.testing import probe_connection
from modules.market_data.research_store import ResearchDataStore
from modules.research.quantitative_features import (
    build_features,
    candle_frame,
    point_in_time_context,
)
from modules.strategies.ai_workflow import StrategyHypothesis
from modules.strategies.signals import strategy_feature_series, strategy_features
from tests.unit.test_pair_strategy_library import history
from tests.unit.test_strategy_trade_setup import strategy


def test_archive_is_immutable_owner_scoped_and_verified(tmp_path):
    first = ResearchDataStore(tmp_path, uuid4())
    reference = first.json({"close": 2})
    assert first.get(reference) == b'{"close":2}'
    assert first.json({"close": 2}) == reference
    second = ResearchDataStore(tmp_path, uuid4())
    with pytest.raises(FileNotFoundError):
        second.get(reference)
    with pytest.raises(ValueError):
        first.get({**reference, "checksum": "../unsafe"})


def test_decode_observed_bid_ask_with_explicit_scale():
    hour = datetime(2024, 1, 2, 12, tzinfo=UTC)
    raw = lzma.compress(struct.pack(">IIIff", 1234, 110002, 110000, 1.0, 2.0))
    result = decode_ticks(raw, hour, Decimal(100000))
    assert result[0]["bid"] == 1.1
    assert result[0]["ask"] == 1.10002
    assert result[0]["time"] == hour + timedelta(milliseconds=1234)
    with pytest.raises(ValueError):
        decode_ticks(raw, hour, Decimal(0))
    with pytest.raises(ValueError):
        decode_ticks(lzma.compress(b"invalid"), hour, Decimal(100000))


async def test_duka_hourly_paths_zero_based_month_and_no_forward_bar(tmp_path):
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(
            200,
            content=lzma.compress(
                struct.pack(">IIIff", 0, 110002, 110000, 1, 1)
                + struct.pack(">IIIff", 3599000, 110102, 110100, 1, 1)
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        candles, source = await dukascopy_history(
            "EURUSD",
            start,
            start + timedelta(hours=1),
            "1h",
            scale=Decimal(100000),
            archive=ResearchDataStore(tmp_path, uuid4()),
            client=client,
        )
    assert requests == ["/datafeed/EURUSD/2024/00/02/12h_ticks.bi5"]
    assert len(candles) == 1 and candles[0].volume == 2
    assert source["price_basis"] == "MID"
    assert source["partitions"][0]["tick_count"] == 2


def test_internal_features_are_causal_and_warmup_is_unknown():
    import pandas as pd

    candles = history(150)
    short = build_features(candles[:80], 60)
    longer = build_features(candles, 60)
    pd.testing.assert_frame_equal(short, longer.iloc[:80])
    assert short.iloc[0].isna()["atr"]
    assert short.index[0] == candles[0].observed_at + timedelta(minutes=1)
    assert {
        "atr",
        "adx",
        "rsi",
        "ema",
        "sma",
        "macd",
        "bb_width",
        "stoch_k",
        "roc",
        "obv",
        "cci",
        "willr",
        "trange",
        "swing_high",
        "sweep_high",
        "london_range",
    }.issubset(short.columns)


def test_confirmed_swing_only_appears_after_two_completed_bars():
    candles = history(20)
    candles[8] = candles[8].model_copy(update={"high": Decimal(140)})
    frame = build_features(candles, 60)
    assert frame.iloc[9].swing_high != 140
    assert frame.iloc[10].swing_high == 140


def test_context_join_uses_availability_not_observation_date():
    frame = candle_frame(history(5), 60)
    publication = frame.index[3].isoformat()
    result = point_in_time_context(
        frame,
        [{"observed_at": frame.index[0].isoformat(), "available_at": publication, "net": 12}],
        value="net",
        name="positioning",
    )
    assert result.positioning.iloc[:3].isna().all()
    assert result.positioning.iloc[3] == 12
    assert result.index.equals(frame.index)


def test_positioning_rolling_features_never_publish_on_tuesday():
    first = datetime(2025, 1, 7, tzinfo=UTC)
    rows = [
        {
            "report_date_as_yyyy_mm_dd": (first + timedelta(weeks=i)).isoformat(),
            "long": 100 + i * 5,
            "short": 50,
            "open_interest_all": 500,
        }
        for i in range(20)
    ]
    seen = first + timedelta(weeks=21)
    result = positioning_features(rows, long_field="long", short_field="short", available_at=seen)
    assert result[-1]["net"] == 145
    assert result[-1]["weekly_change"] == 5
    assert result[-1]["long_short_ratio"] == 3.9
    assert result[-1]["percentile"] is not None
    assert result[0]["percentile"] is None
    assert all(r["available_at"] == seen.isoformat() for r in result)


async def test_cftc_exact_contract_query_and_health_not_mt5():
    paths = []

    def respond(request):
        paths.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "cftc_contract_market_code": "099741",
                    "report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00",
                }
            ],
        )

    async with httpx.AsyncClient(
        base_url="https://publicreporting.cftc.gov", transport=httpx.MockTransport(respond)
    ) as client:
        rows = await CftcProvider(client).cot("099741", report="TFF")
        probe = await probe_connection(
            ConnectionProfile(name="COT", provider="CFTC"), None, client=client
        )
    assert len(rows) == 1 and probe.status == "HEALTHY"
    assert "CFTC_COT" in probe.capabilities
    assert "bridge" not in str(paths[1].url)
    assert paths[0].url.params["$where"] == "cftc_contract_market_code='099741'"


async def test_ecb_csv_normalizes_without_claiming_publication_dates():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text="TIME_PERIOD,OBS_VALUE,UNIT\n2026-09-22,1.1,USD\n"
            )
        )
    ) as client:
        data = await ecb_series(
            "EXR",
            "D.USD.EUR.SP00.A",
            datetime(2026, 9, 1, tzinfo=UTC),
            datetime(2026, 9, 23, tzinfo=UTC),
            client=client,
        )
    assert data["observations"][0]["OBS_VALUE"] == "1.1"
    assert data["point_in_time"] == "FIRST_SEEN_ONLY"
    assert data["authority"] == "CONTEXT_ONLY"


@pytest.mark.parametrize("provider", ["DUKASCOPY", "CCXT", "YAHOO_FINANCE", "ECB", "CFTC"])
def test_public_research_connections_do_not_accept_private_credentials(provider):
    with pytest.raises(ValueError, match="private credentials"):
        ConnectionProfile(name="Public", provider=provider, credential_id=uuid4())


def test_atr_parameters_are_shared_and_causal():
    import numpy as np
    import talib

    candles = history(80)
    spec = strategy(parameters={"atr_period": 14, "structure_window": 10})
    computed = strategy_features(spec, candles, 60)
    expected = talib.ATR(
        *[
            np.array([float(getattr(c, key)) for c in candles[:61]])
            for key in ("high", "low", "close")
        ],
        14,
    )[-1]
    assert float(computed["volatility"]) == pytest.approx(expected)
    assert computed["prior_high"] == max(c.high for c in candles[50:60])
    with pytest.raises(ValueError):
        strategy(parameters={"atr_period": "2.5"})


def test_vectorbt_sweep_runs_real_engine_on_discovery_only():
    hypothesis = StrategyHypothesis(
        hypothesis_id="H1",
        specification=strategy(),
        rationale="Test",
        breakdown=["Signal", "Stop", "Validation"],
        agent_id="deterministic_test",
        evidence_refs=["history:test"],
    )
    chosen, report = parameter_sweep(
        [hypothesis],
        history(150),
        BacktestConfiguration(initial_equity=10000, spread=".01", slippage=".01"),
        timeframe_seconds=60,
        max_combinations=16,
    )
    assert report["engine"] == "vectorbt" and report["status"] == "COMPLETED"
    assert report["combination_count"] == 16
    assert report["outer_holdout_used"] is False
    assert report["approved_for_execution"] is False
    assert len(chosen) == 1
    assert all("inner_validation" in result for result in report["experiments"])


def test_native_nautilus_order_lifecycle_with_costs_and_partial_targets():
    from modules.backtesting.nautilus_validation import validate_execution

    result = validate_execution(
        strategy(),
        history(120),
        BacktestConfiguration(initial_equity=10000, spread=".02", slippage=".01", commission=".01"),
        timeframe_seconds=60,
        contract={
            "tick_size": ".01",
            "price_currency": "USD",
            "quantity_step": ".01",
            "quantity_minimum": ".01",
            "contract_multiplier": "1",
        },
    )
    assert result["engine"] == "NautilusTrader"
    assert result["status"] == "COMPLETED"
    assert result["trade_count"] >= 2
    assert result["open_position_count"] == 0
    assert result["rejections"] == []
    assert result["fills"]
    assert any(position["partial_targets_hit"] >= 1 for position in result["closed_positions"])
    assert result["data_basis"].startswith("ASSUMED_OHLC")
    assert result["execution_authorized"] is False
    assert Decimal(result["intrabar_max_drawdown"]) > 0


def test_missing_broker_contract_cannot_pass_native_validation():
    from modules.backtesting.nautilus_validation import validate_execution

    result = validate_execution(
        strategy(),
        history(80),
        BacktestConfiguration(initial_equity=10000),
        timeframe_seconds=60,
        contract={},
    )
    assert result["passed"] is False
    assert result["status"] == "MISSING_BROKER_CONTRACT_TERMS"


async def test_duka_cannot_build_four_hour_bar_from_missing_source_hour(tmp_path):
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)

    def respond(request):
        if request.url.path.endswith("13h_ticks.bi5"):
            return httpx.Response(404)
        return httpx.Response(
            200, content=lzma.compress(struct.pack(">IIIff", 0, 110002, 110000, 1, 1))
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match="complete source-hour"):
            await dukascopy_history(
                "EURUSD",
                start,
                start + timedelta(hours=4),
                "4h",
                scale=Decimal(100000),
                archive=ResearchDataStore(tmp_path, uuid4()),
                client=client,
            )


def test_missing_cot_week_is_not_reported_as_weekly_or_four_week_change():
    first = datetime(2025, 1, 7, tzinfo=UTC)
    rows = [
        {
            "report_date_as_yyyy_mm_dd": (first + timedelta(weeks=i)).isoformat(),
            "long": i * 5,
            "short": 0,
        }
        for i in (0, 1, 2, 3, 5)
    ]
    result = positioning_features(rows, long_field="long", short_field="short")
    assert result[-1]["weekly_change"] is None
    assert result[-1]["momentum_4w"] is None


@pytest.mark.parametrize("period", [None, 14, 30])
def test_linear_batch_features_match_every_causal_prefix(period):
    parameters = {"structure_window": 30}
    if period is not None:
        parameters["atr_period"] = period
    spec, candles = strategy(parameters=parameters), history(150)
    series = strategy_feature_series(spec, candles)
    assert series == [strategy_features(spec, candles, i) for i in range(len(candles))]
    assert series[:80] == strategy_feature_series(spec, candles[:80])


async def test_ccxt_aggregates_only_complete_four_hour_candles_and_closes(monkeypatch):
    import ccxt.async_support as ccxt

    start = datetime(2026, 9, 21, tzinfo=UTC)
    seen = []

    class Exchange:
        markets = {"BTC/USDT:USDT": {"type": "swap"}}
        has = {"fetchOHLCV": True}
        timeframes = {"1h": True}

        def __init__(self, *_):
            pass

        async def load_markets(self):
            pass

        async def fetch_ohlcv(self, symbol, timeframe, **kwargs):
            seen.append(timeframe)
            if len(seen) > 1:
                return []
            return [
                [
                    int((start + timedelta(hours=i)).timestamp() * 1000),
                    100 + i,
                    103 + i,
                    99 + i,
                    101 + i,
                    10,
                ]
                for i in range(7)
            ]

        async def close(self):
            seen.append("CLOSED")

    monkeypatch.setattr(ccxt, "binanceusdm", Exchange)
    candles, source = await ccxt_history(
        "binanceusdm", "BTC/USDT:USDT", start, start + timedelta(hours=8), "4h"
    )
    assert len(candles) == 1
    assert candles[0].observed_at == start and candles[0].volume == 40
    assert source["native_timeframe"] == "1h"
    assert seen[-1] == "CLOSED"


def test_indicator_rules_share_stored_features_and_reject_unknown_warmup():
    from modules.strategies.ai_workflow import SUPPORTED_FEATURES, allowed_condition_values
    from modules.strategies.compiler import compile_strategy
    from modules.strategies.signals import entry_matches
    from modules.strategies.trade_setup import build_strategy_setup

    candles = history(120)
    spec = strategy(
        entry=[{"feature": "rsi", "operator": ">", "value": "70"}],
        confirmations=[{"feature": "close", "operator": ">", "value": "sma"}],
        parameters={"atr_period": 14},
    )
    assert {"rsi", "sma", "macd", "adx", "stoch_k"}.issubset(SUPPORTED_FEATURES)
    assert "70" in allowed_condition_values({})
    series = strategy_feature_series(spec, candles)
    frame = build_features(candles, 60)
    for index in (40, 80, 119):
        point = strategy_features(spec, candles, index)
        assert point == series[index]
        assert point["rsi"] == Decimal(str(frame.rsi.iloc[index]))
        assert point["sma"] == Decimal(str(frame.sma.iloc[index]))
    assert not entry_matches(spec, series[0])
    assert entry_matches(spec, series[-1])
    assert compile_strategy(spec).evaluate(series[-1])
    setup = build_strategy_setup(
        spec, candles, now=candles[-1].observed_at + timedelta(minutes=1), timeframe_seconds=60
    )
    assert setup["status"] == "SIGNAL"
    altered = [
        *candles[:-1],
        candles[-1].model_copy(update={"close": Decimal(400), "high": Decimal(500)}),
    ]
    assert strategy_feature_series(spec, altered)[40] == series[40]
