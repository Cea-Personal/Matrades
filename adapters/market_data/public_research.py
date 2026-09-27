"""Public research feeds. No account, order or private exchange methods exist here."""

from __future__ import annotations

import asyncio
import io
import lzma
import math
import re
import struct
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx

from modules.backtesting.engine import BacktestCandle
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import ResolvedConnection
from modules.market_data.research_store import ResearchDataStore

if TYPE_CHECKING:
    from pandas import DataFrame

SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
EXCHANGES = {"coinbase", "binance", "binanceusdm", "kraken", "okx", "bybit"}
COT_DATASETS = {"LEGACY": "6dca-aqww", "TFF": "gpe5-46if", "DISAGGREGATED": "72hh-3qpy"}


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("research timestamps must be timezone-aware")
    return value.astimezone(UTC)


def decode_ticks(payload: bytes, hour: datetime, scale: Decimal) -> list[dict]:
    if not scale.is_finite() or scale <= 0:
        raise ValueError("a verified positive instrument price_scale is required")
    decoder = lzma.LZMADecompressor()
    raw = decoder.decompress(payload, max_length=20_000_001)
    if not decoder.eof or len(raw) > 20_000_000 or len(raw) % 20:
        raise ValueError("invalid or oversized Dukascopy tick partition")
    rows = []
    for ms, ask, bid, av, bv in struct.iter_unpack(">IIIff", raw):
        if (
            ms >= 3_600_000
            or not 0 < bid <= ask
            or not all(math.isfinite(v) and v >= 0 for v in (av, bv))
        ):
            raise ValueError("invalid Dukascopy tick")
        rows.append(
            {
                "time": hour + timedelta(milliseconds=ms),
                "bid": float(Decimal(bid) / scale),
                "ask": float(Decimal(ask) / scale),
                "bid_size": bv,
                "ask_size": av,
            }
        )
    if any(a["time"] > b["time"] for a, b in zip(rows, rows[1:], strict=False)):
        raise ValueError("unordered Dukascopy ticks")
    return rows


async def dukascopy_history(
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str,
    *,
    scale: Decimal,
    archive: ResearchDataStore,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[BacktestCandle], dict]:
    import pandas as pd

    if not re.fullmatch(r"[A-Z0-9_]{3,32}", symbol) or timeframe not in SECONDS:
        raise ValueError("invalid Dukascopy instrument or timeframe")
    start, end = utc(start), utc(end)
    if not timedelta(0) < end - start <= timedelta(days=366):
        raise ValueError("history imports are bounded to one year per request")
    semaphore = asyncio.Semaphore(6)
    owns = client is None
    http = client or httpx.AsyncClient(timeout=30)
    hours = []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor + timedelta(hours=1) <= end:
        hours.append(cursor)
        cursor += timedelta(hours=1)

    async def partition(hour: datetime) -> tuple[DataFrame | None, dict[str, Any]]:
        path = (
            f"{symbol}/{hour.year}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"
        )
        async with semaphore:
            response = await http.get(f"https://datafeed.dukascopy.com/datafeed/{path}")
        if response.status_code == 404:
            return None, {"hour": hour.isoformat(), "status": "MISSING"}
        response.raise_for_status()
        if not response.content:
            return None, {"hour": hour.isoformat(), "status": "EMPTY"}
        ticks = decode_ticks(response.content, hour, scale)
        raw = archive.put(response.content, layer="raw", extension="bi5")
        if not ticks:
            return None, {"hour": hour.isoformat(), "status": "EMPTY", "raw": raw}
        frame = pd.DataFrame(ticks).set_index("time")
        frame["mid"] = (frame.bid + frame.ask) / 2
        frame["spread"] = frame.ask - frame.bid
        bars = frame.mid.resample(f"{SECONDS[timeframe]}s").ohlc()
        bars["volume"] = frame.mid.resample(f"{SECONDS[timeframe]}s").count()
        bars["spread_mean"] = frame.spread.resample(f"{SECONDS[timeframe]}s").mean()
        bars["spread_max"] = frame.spread.resample(f"{SECONDS[timeframe]}s").max()
        return bars, {
            "hour": hour.isoformat(),
            "status": "PRESENT",
            "raw": raw,
            "tick_count": len(ticks),
            "price_scale": str(scale),
        }

    try:
        # Bounded chunks avoid creating thousands of simultaneous requests / tick frames.
        partitions = []
        frames = []
        for offset in range(0, len(hours), 24):
            for frame, metadata in await asyncio.gather(
                *(partition(h) for h in hours[offset : offset + 24])
            ):
                partitions.append(metadata)
                if frame is not None:
                    frames.append(frame)
        if not frames:
            raise ValueError("Dukascopy returned no history for the mapped instrument")
        joined = pd.concat(frames).sort_index()
        bars = (
            joined.resample(f"{SECONDS[timeframe]}s")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "spread_mean": "mean",
                    "spread_max": "max",
                }
            )
            .dropna(subset=["open", "close"])
        )
        bars = bars[
            (bars.index >= start) & (bars.index + pd.Timedelta(seconds=SECONDS[timeframe]) <= end)
        ]
        # A 4h/daily candle cannot silently aggregate only some of its source hours.
        known_hours = {
            datetime.fromisoformat(p["hour"])
            for p in partitions
            if p["status"] in {"PRESENT", "EMPTY"}
        }
        incomplete_buckets = []
        complete = []
        for at in bars.index:
            left = at.to_pydatetime().replace(minute=0, second=0, microsecond=0)
            right = at.to_pydatetime() + timedelta(seconds=SECONDS[timeframe])
            missing = False
            while left < right:
                if left not in known_hours:
                    missing = True
                    break
                left += timedelta(hours=1)
            complete.append(not missing)
            if missing:
                incomplete_buckets.append(at.isoformat())
        bars = bars[complete]
        if bars.empty:
            raise ValueError("Dukascopy returned no complete source-hour candle buckets")
        candles = [
            BacktestCandle(
                observed_at=at.to_pydatetime(),
                **{
                    key: Decimal(str(row[key]))
                    for key in ("open", "high", "low", "close", "volume")
                },
            )
            for at, row in bars.iterrows()
        ]
        return candles, {
            "provider": "DUKASCOPY",
            "symbol": symbol,
            "timeframe": timeframe,
            "authority": "INDEPENDENT_RESEARCH",
            "price_basis": "MID",
            "volume_unit": "TICK_COUNT",
            "partitions": partitions,
            "incomplete_buckets": incomplete_buckets,
            "normalized": archive.frame(bars),
            "price_scale": str(scale),
            "source_version": "dukascopy-hourly-bi5-v1",
        }
    finally:
        if owns:
            await http.aclose()


async def ccxt_history(
    exchange_id: str, symbol: str, start: datetime, end: datetime, timeframe: str
):
    import ccxt.async_support as ccxt

    if exchange_id not in EXCHANGES or timeframe not in SECONDS:
        raise ValueError("unsupported public exchange or timeframe")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 15000})
    try:
        await exchange.load_markets()
        if symbol not in exchange.markets or not exchange.has.get("fetchOHLCV"):
            raise ValueError("exchange does not support mapped instrument OHLCV")
        native_timeframe = timeframe
        if (
            timeframe == "4h"
            and timeframe not in exchange.timeframes
            and "1h" in exchange.timeframes
        ):
            native_timeframe = "1h"
        elif timeframe not in exchange.timeframes:
            raise ValueError("exchange does not support requested timeframe")
        cursor, until = int(utc(start).timestamp() * 1000), int(utc(end).timestamp() * 1000)
        rows = {}
        for _ in range(100):
            batch = await exchange.fetch_ohlcv(symbol, native_timeframe, since=cursor, limit=1000)
            if not batch:
                break
            for row in batch:
                if cursor <= row[0] and row[0] + SECONDS[native_timeframe] * 1000 <= until:
                    rows[row[0]] = row
            next_cursor = max(row[0] for row in batch) + SECONDS[native_timeframe] * 1000
            if next_cursor <= cursor:
                raise ValueError("exchange history pagination made no progress")
            cursor = next_cursor
            if cursor >= until:
                break
        else:
            raise ValueError("exchange history pagination budget exhausted; import smaller chunks")
        candles = [
            BacktestCandle(
                observed_at=datetime.fromtimestamp(row[0] / 1000, UTC),
                **dict(
                    zip(
                        ("open", "high", "low", "close", "volume"),
                        map(lambda x: Decimal(str(x)), row[1:6]),
                        strict=True,
                    )
                ),
            )
            for _, row in sorted(rows.items())
        ]
        if native_timeframe != timeframe:
            # Complete UTC buckets only; no partial 4h bar or invented missing hours.
            grouped = {}
            for candle in candles:
                bucket = (
                    int(candle.observed_at.timestamp()) // SECONDS[timeframe] * SECONDS[timeframe]
                )
                grouped.setdefault(bucket, []).append(candle)
            candles = [
                BacktestCandle(
                    observed_at=datetime.fromtimestamp(bucket, UTC),
                    open=parts[0].open,
                    high=max(c.high for c in parts),
                    low=min(c.low for c in parts),
                    close=parts[-1].close,
                    volume=sum((c.volume for c in parts), Decimal(0)),
                )
                for bucket, parts in sorted(grouped.items())
                if len(parts) == 4
                and [int(c.observed_at.timestamp()) for c in parts]
                == [bucket + i * 3600 for i in range(4)]
                and bucket >= start.timestamp()
                and bucket + SECONDS[timeframe] <= end.timestamp()
            ]
        return candles, {
            "provider": "CCXT",
            "exchange": exchange_id,
            "symbol": symbol,
            "source_version": ccxt.__version__,
            "authority": "INDEPENDENT_RESEARCH",
            "market_type": exchange.markets[symbol]["type"],
            "native_timeframe": native_timeframe,
            "timeframe": timeframe,
        }
    finally:
        await exchange.close()


async def crypto_context(exchange_id: str, symbol: str) -> dict:
    import ccxt.async_support as ccxt

    if exchange_id not in EXCHANGES:
        raise ValueError("unsupported public exchange")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 15000})
    try:
        await exchange.load_markets()
        market = exchange.market(symbol)
        result = {
            "exchange": exchange_id,
            "symbol": symbol,
            "market_type": market["type"],
            "available_at": datetime.now(UTC).isoformat(),
            "authority": "CONTEXT_ONLY",
        }
        for capability, method in (
            ("fetchTicker", exchange.fetch_ticker),
            ("fetchTrades", exchange.fetch_trades),
            ("fetchOrderBook", exchange.fetch_order_book),
            ("fetchFundingRate", exchange.fetch_funding_rate),
            ("fetchOpenInterest", exchange.fetch_open_interest),
        ):
            if capability in {"fetchFundingRate", "fetchOpenInterest"} and not market["contract"]:
                continue
            if exchange.has.get(capability):
                result[capability] = await method(symbol)
        if market["contract"] and exchange.has.get("fetchFundingRateHistory"):
            result["funding_history"] = await exchange.fetch_funding_rate_history(
                symbol, limit=1000
            )
        if market["contract"] and exchange.has.get("fetchOpenInterestHistory"):
            result["open_interest_history"] = await exchange.fetch_open_interest_history(
                symbol, timeframe="1h", limit=30
            )
        if exchange_id == "binanceusdm":
            # Only the non-unified premium/basis endpoints use direct public requests.
            async with httpx.AsyncClient(base_url="https://fapi.binance.com", timeout=15) as http:
                for name, path, params in (
                    ("premium", "/fapi/v1/premiumIndex", {"symbol": market["id"]}),
                    (
                        "basis",
                        "/futures/data/basis",
                        {
                            "pair": market["id"],
                            "contractType": "PERPETUAL",
                            "period": "1h",
                            "limit": 30,
                        },
                    ),
                    (
                        "open_interest_history",
                        "/futures/data/openInterestHist",
                        {"symbol": market["id"], "period": "1h", "limit": 30},
                    ),
                ):
                    response = await http.get(path, params=params)
                    response.raise_for_status()
                    result[name] = response.json()
        return result
    finally:
        await exchange.close()


async def yahoo_history(symbol: str, start: datetime, end: datetime, timeframe: str):
    import yfinance as yf

    interval = {"1h": "1h", "1d": "1d"}.get(timeframe)
    if interval is None:
        raise ValueError("intermarket Yahoo history supports 1h and 1d only")

    def fetch():
        return yf.Ticker(symbol).history(
            start=utc(start),
            end=utc(end),
            interval=interval,
            auto_adjust=False,
            actions=True,
            raise_errors=True,
        )

    frame = await asyncio.to_thread(fetch)
    if frame.empty:
        raise ValueError("Yahoo returned no intermarket history")
    candles = [
        BacktestCandle(
            observed_at=at.to_pydatetime().astimezone(UTC),
            **{
                key.lower(): Decimal(str(row[key]))
                for key in ("Open", "High", "Low", "Close", "Volume")
            },
        )
        for at, row in frame.iterrows()
        if all(math.isfinite(row[k]) for k in ("Open", "High", "Low", "Close", "Volume"))
    ]
    return candles, {
        "provider": "YAHOO_FINANCE",
        "symbol": symbol,
        "source_version": yf.__version__,
        "authority": "CONTEXT_ONLY",
        "corporate_actions": frame[["Dividends", "Stock Splits"]].to_json(),
        "limitations": [
            "Unadjusted proxy prices; not executable broker data",
            "Intraday history is provider-limited",
        ],
    }


async def ecb_series(
    flow: str, key: str, start: datetime, end: datetime, *, client: httpx.AsyncClient | None = None
) -> dict:
    import pandas as pd

    if not re.fullmatch(r"[A-Z0-9_]{2,20}", flow) or not re.fullmatch(
        r"[A-Za-z0-9_.+-]{1,150}", key
    ):
        raise ValueError("invalid ECB SDMX series")
    owns = client is None
    http = client or httpx.AsyncClient(timeout=30)
    try:
        response = await http.get(
            f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}",
            params={
                "format": "csvdata",
                "startPeriod": utc(start).date().isoformat(),
                "endPeriod": utc(end).date().isoformat(),
            },
        )
        response.raise_for_status()
        frame = pd.read_csv(io.StringIO(response.text), dtype=str)
        if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(frame.columns):
            raise ValueError("ECB response lacks SDMX observation fields")
        return {
            "provider": "ECB",
            "flow": flow,
            "key": key,
            "authority": "CONTEXT_ONLY",
            "available_at": datetime.now(UTC).isoformat(),
            "observations": frame.fillna("").to_dict("records"),
            "point_in_time": "FIRST_SEEN_ONLY",
            "raw_csv": response.text,
        }
    finally:
        if owns:
            await http.aclose()


async def public_history(
    connection: ResolvedConnection,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str,
    archive: ResearchDataStore,
):
    provider, config = connection.profile.provider, connection.profile.configuration
    mapping = config.get("symbol_map", {}).get(symbol)
    if not isinstance(mapping, dict) or not mapping.get("symbol"):
        raise ValueError("independent history requires an explicit broker-to-research symbol_map")
    research_symbol = str(mapping["symbol"])
    if provider == ConnectionProvider.DUKASCOPY:
        if not mapping.get("price_scale"):
            raise ValueError("Dukascopy mapping requires verified price_scale, including metals")
        return await dukascopy_history(
            research_symbol,
            start,
            end,
            timeframe,
            scale=Decimal(str(mapping["price_scale"])),
            archive=archive,
        )
    if provider == ConnectionProvider.CCXT:
        return await ccxt_history(
            str(config.get("exchange", "coinbase")), research_symbol, start, end, timeframe
        )
    if provider == ConnectionProvider.YAHOO_FINANCE:
        return await yahoo_history(research_symbol, start, end, timeframe)
    raise ValueError("provider is not a public historical price source")
