"""Causal internal TA-Lib and custom features; unknowns remain NaN, never invented."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.backtesting.engine import BacktestCandle

FEATURE_VERSION = "talib-structure-session-intermarket-v1"
TECHNICAL_FEATURES = frozenset(
    {
        "atr",
        "adx",
        "rsi",
        "ema",
        "sma",
        "roc",
        "obv",
        "cci",
        "willr",
        "trange",
        "macd",
        "macd_signal",
        "macd_histogram",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "stoch_k",
        "stoch_d",
        "bb_width",
    }
)


def candle_frame(candles: list[BacktestCandle], timeframe_seconds: int):
    import pandas as pd

    from modules.backtesting.engine import validate_candles

    validate_candles(candles, minimum=1)
    frame = pd.DataFrame(
        [
            {
                "time": item.observed_at,
                **{
                    key: float(getattr(item, key))
                    for key in ("open", "high", "low", "close", "volume")
                },
            }
            for item in candles
        ]
    ).set_index("time")
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    # Features are knowable at bar CLOSE, not at its opening timestamp.
    frame.index += pd.Timedelta(seconds=timeframe_seconds)
    frame.index.name = "available_at"
    return frame


def technical_features(frame):
    """Same causal technical definitions for feature storage and trading rules."""
    import talib

    h, lows, c, v = (frame[key].to_numpy(dtype=float) for key in ("high", "low", "close", "volume"))
    output = frame.copy()
    for name, values in {
        "atr": talib.ATR(h, lows, c, 14),
        "adx": talib.ADX(h, lows, c, 14),
        "rsi": talib.RSI(c, 14),
        "ema": talib.EMA(c, 20),
        "sma": talib.SMA(c, 20),
        "roc": talib.ROC(c, 10),
        "obv": talib.OBV(c, v),
        "cci": talib.CCI(h, lows, c, 14),
        "willr": talib.WILLR(h, lows, c, 14),
        "trange": talib.TRANGE(h, lows, c),
    }.items():
        output[name] = values
    output["macd"], output["macd_signal"], output["macd_histogram"] = talib.MACD(c)
    output["bb_upper"], output["bb_middle"], output["bb_lower"] = talib.BBANDS(c, 20)
    output["stoch_k"], output["stoch_d"] = talib.STOCH(h, lows, c)
    output["bb_width"] = (output.bb_upper - output.bb_lower) / output.bb_middle
    return output


def build_features(
    candles: list[BacktestCandle],
    timeframe_seconds: int,
    *,
    intermarket: dict | None = None,
    as_of: datetime | None = None,
):
    import numpy as np
    import pandas as pd
    import talib

    frame = candle_frame(candles, timeframe_seconds)
    if as_of is not None:
        frame = frame[frame.index <= as_of]
    if frame.empty:
        raise ValueError("no completed candles at the research cutoff")
    output = technical_features(frame)
    c = frame.close.to_numpy(dtype=float)
    moves = frame.close.diff()
    output["efficiency"] = frame.close.diff(20).abs() / moves.abs().rolling(20).sum()
    output["trend_slope"] = frame.close.pct_change(20) / 20
    output["ma_separation"] = (talib.EMA(c, 10) - talib.EMA(c, 30)) / frame.close
    output["realized_volatility"] = np.log(frame.close).diff().rolling(20).std(ddof=0)
    output["volatility_expansion"] = output.atr / output.atr.rolling(60, min_periods=20).mean()
    output["volatility_contraction"] = output.volatility_expansion < 0.75
    output["atr_percentile"] = output.atr.rolling(100, min_periods=20).rank(pct=True)
    output["historical_volatility_percentile"] = output.realized_volatility.rolling(
        100, min_periods=20
    ).rank(pct=True)
    output["range_high"] = frame.high.shift(1).rolling(20).max()
    output["range_low"] = frame.low.shift(1).rolling(20).min()
    output["distance_high"] = (output.range_high - frame.close) / output.atr
    output["distance_low"] = (frame.close - output.range_low) / output.atr
    # A 5-bar pivot is recorded only 2 bars AFTER the pivot, when it is confirmed.
    high_pivot = frame.high.shift(2).where(frame.high.shift(2) == frame.high.rolling(5).max())
    low_pivot = frame.low.shift(2).where(frame.low.shift(2) == frame.low.rolling(5).min())
    output["swing_high"] = high_pivot.ffill()
    output["swing_low"] = low_pivot.ffill()
    prior_high = high_pivot.ffill().shift(1)
    prior_low = low_pivot.ffill().shift(1)
    output["higher_high"] = high_pivot > prior_high
    output["lower_high"] = high_pivot < prior_high
    output["higher_low"] = low_pivot > prior_low
    output["lower_low"] = low_pivot < prior_low
    output["bos_up"] = frame.close > output.swing_high.shift(1)
    output["bos_down"] = frame.close < output.swing_low.shift(1)
    tolerance = output.atr * 0.05
    output["equal_highs"] = (frame.high - output.range_high).abs() <= tolerance
    output["equal_lows"] = (frame.low - output.range_low).abs() <= tolerance
    output["sweep_high"] = (frame.high > output.range_high) & (frame.close < output.range_high)
    output["sweep_low"] = (frame.low < output.range_low) & (frame.close > output.range_low)
    output["rejection_up"] = (frame.high - np.maximum(frame.open, frame.close)) / (
        frame.high - frame.low
    )
    output["rejection_down"] = (np.minimum(frame.open, frame.close) - frame.low) / (
        frame.high - frame.low
    )
    output["volume_anomaly"] = frame.volume / frame.volume.shift(1).rolling(20).mean()
    session_times = frame.index - pd.Timedelta(seconds=timeframe_seconds)
    day = session_times.floor("D")
    previous = frame.groupby(day).agg({"high": "max", "low": "min"}).shift(1)
    output["previous_day_high"] = day.map(previous.high)
    output["previous_day_low"] = day.map(previous.low)
    # Per-session running range, DST-aware. No completed-day/session future values.
    for name, zone, start, end in (
        ("asia", "Asia/Tokyo", 9, 17),
        ("london", "Europe/London", 8, 17),
        ("new_york", "America/New_York", 8, 17),
    ):
        local = session_times.tz_convert(zone)
        in_session = (local.hour >= start) & (local.hour < end)
        days = local.date
        highs = frame.high.where(in_session).groupby(days).cummax()
        lows = frame.low.where(in_session).groupby(days).cummin()
        output[f"{name}_high"] = highs.groupby(days).ffill()
        output[f"{name}_low"] = lows.groupby(days).ffill()
        output[f"{name}_range"] = output[f"{name}_high"] - output[f"{name}_low"]
        session_returns = np.log(frame.close).diff().where(in_session)
        output[f"{name}_volatility"] = (
            session_returns.groupby(days)
            .expanding(min_periods=2)
            .std()
            .reset_index(level=0, drop=True)
            .reindex(frame.index)
        )
        output[f"{name}_active"] = in_session
    output["behaviour"] = np.where(output.efficiency >= 0.35, "TRENDING", "RANGING")
    output.loc[output.efficiency.isna(), "behaviour"] = "UNKNOWN"
    output["direction"] = np.where(output.trend_slope > 0, "BULLISH", "BEARISH")
    output.loc[output.trend_slope == 0, "direction"] = "FLAT"
    output.loc[output.trend_slope.isna(), "direction"] = "UNKNOWN"
    output["volatility_regime"] = np.select(
        [output.volatility_expansion >= 1.5, output.volatility_expansion <= 0.75],
        ["HIGH_VOLATILITY", "LOW_VOLATILITY"],
        default="NORMAL_VOLATILITY",
    )
    output.loc[output.volatility_expansion.isna(), "volatility_regime"] = "UNKNOWN"
    output["regime"] = output.behaviour + ":" + output.direction + ":" + output.volatility_regime
    for name, proxy in (intermarket or {}).items():
        if not name.isidentifier() or not isinstance(proxy.index, pd.DatetimeIndex):
            raise ValueError("intermarket input requires named UTC availability-indexed prices")
        if (
            proxy.index.tz is None
            or not proxy.index.is_unique
            or not proxy.index.is_monotonic_increasing
        ):
            raise ValueError("intermarket proxy availability must be aware, ordered and unique")
        # No future joins or unlimited stale daily/intraday context.
        aligned = proxy.reindex(frame.index, method="ffill", tolerance=pd.Timedelta("3d"))
        returns = frame.close.pct_change(fill_method=None)
        proxy_returns = aligned.pct_change(fill_method=None)
        output[f"{name}_correlation"] = returns.rolling(60, min_periods=20).corr(proxy_returns)
        output[f"{name}_beta"] = (
            returns.rolling(60, min_periods=20).cov(proxy_returns)
            / proxy_returns.rolling(60, min_periods=20).var()
        )
        output[f"{name}_relative_strength"] = frame.close.pct_change(
            20, fill_method=None
        ) - aligned.pct_change(20, fill_method=None)
        left_change, right_change = frame.close.diff(20), aligned.diff(20)
        output[f"{name}_divergence"] = (np.sign(left_change) != np.sign(right_change)).where(
            left_change.notna() & right_change.notna()
        )
        # Proxy direction is labelled; it is not a universal risk-on/risk-off inference.
        output[f"{name}_risk_proxy_direction"] = np.sign(aligned.diff(20))
    output = output.replace([np.inf, -np.inf], np.nan)
    output.attrs.update(
        feature_version=FEATURE_VERSION,
        ta_lib_version=talib.__version__,
        volume_semantics="SOURCE_SPECIFIC_NOT_CROSS_PROVIDER_LIQUIDITY",
    )
    return output


def point_in_time_context(frame, observations: list[dict], *, value: str, name: str):
    """Join only published/first-seen context. A report date is not an availability key."""
    import pandas as pd

    rows = pd.DataFrame(observations)
    if rows.empty:
        return frame
    if "available_at" not in rows or value not in rows:
        raise ValueError("context requires an explicit availability time and value")
    rows["available_at"] = pd.to_datetime(rows.available_at, utc=True)
    rows = rows.sort_values("available_at").drop_duplicates("available_at", keep="last")
    left = frame.sort_index().rename_axis("available_at").reset_index()
    return pd.merge_asof(
        left,
        rows[["available_at", value]].rename(columns={value: name}),
        on="available_at",
        direction="backward",
    ).set_index("available_at")
