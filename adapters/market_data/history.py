"""Historical candle retrieval for deterministic backtesting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from adapters.broker.mt5_bridge.client import Mt5BridgeClient
from adapters.market_data.coinbase.client import CoinbaseClient
from adapters.market_data.twelve_data.client import TwelveDataClient
from modules.backtesting.engine import BacktestCandle
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import ResolvedConnection

TIMEFRAMES = {
    "1m": ("1min", 60),
    "5m": ("5min", 300),
    "15m": ("15min", 900),
    "1h": ("1h", 3600),
    "4h": ("4h", 14400),
    "1d": ("1day", 86400),
}


async def historical_candles(
    connection: ResolvedConnection,
    symbol: str,
    start_at: datetime,
    end_at: datetime,
    timeframe: str,
    *,
    account_id: UUID | None = None,
) -> tuple[list[BacktestCandle], dict[str, str]]:
    if timeframe not in TIMEFRAMES:
        raise ValueError("unsupported timeframe")
    if start_at >= end_at:
        raise ValueError("backtest start must be before end")
    if connection.profile.provider == ConnectionProvider.MT5_BRIDGE:
        if account_id is None or not connection.secret:
            raise ValueError("MT5 history requires a pinned account and credential")
        client = Mt5BridgeClient(
            str(connection.profile.configuration["bridge_url"]), connection.secret.encode()
        )
        try:
            snapshot = await client.market_data(account_id)
        finally:
            await client.close()
        broker_timeframe = {
            "1m": "M1",
            "5m": "M5",
            "15m": "M15",
            "1h": "H1",
            "4h": "H4",
            "1d": "D1",
        }[timeframe]
        if snapshot.account_id != account_id or snapshot.timeframe != broker_timeframe:
            raise ValueError("MT5 historical account or timeframe does not match research")
        instrument = next((item for item in snapshot.instruments if item.symbol == symbol), None)
        if instrument is None:
            raise ValueError("MT5 historical listing is unavailable")
        candles = [
            BacktestCandle(
                observed_at=item.observed_at,
                open=item.open,
                high=item.high,
                low=item.low,
                close=item.close,
                volume=item.tick_volume,
            )
            for item in sorted(instrument.candles, key=lambda value: value.observed_at)
            if start_at <= item.observed_at <= end_at
        ]
        return candles, {
            "provider": "MT5_BRIDGE",
            "source_version": f"{snapshot.sequence}:{snapshot.timeframe}",
        }
    if connection.profile.provider == ConnectionProvider.TWELVE_DATA:
        if not connection.secret:
            raise RuntimeError("Twelve Data credential unavailable")
        twelve_client = TwelveDataClient(connection.secret)
        try:
            body = await twelve_client.candles(
                symbol,
                interval=TIMEFRAMES[timeframe][0],
                outputsize=500,
                start_date=start_at.isoformat(),
                end_date=end_at.isoformat(),
            )
        finally:
            await twelve_client.close()
        values = body.get("values") or []
        candles = sorted(
            [
                BacktestCandle(
                    observed_at=_parse_twelve_time(str(item["datetime"])),
                    open=Decimal(str(item["open"])),
                    high=Decimal(str(item["high"])),
                    low=Decimal(str(item["low"])),
                    close=Decimal(str(item["close"])),
                    volume=Decimal(str(item.get("volume") or 0)),
                )
                for item in values
            ],
            key=lambda item: item.observed_at,
        )
        return candles, {"provider": "TWELVE_DATA", "source_version": str(body.get("meta", {}))}
    if connection.profile.provider == ConnectionProvider.COINBASE:
        coinbase_client = CoinbaseClient()
        target_seconds = TIMEFRAMES[timeframe][1]
        native_seconds = 3600 if timeframe == "4h" else target_seconds
        # Bound research history to the same 500-bar budget as Twelve Data.
        cursor = max(start_at, end_at - timedelta(seconds=500 * target_seconds))
        rows = {}
        try:
            while cursor < end_at:
                page_end = min(end_at, cursor + timedelta(seconds=299 * native_seconds))
                values = await coinbase_client.candles(
                    symbol,
                    native_seconds,
                    start=cursor.isoformat(),
                    end=page_end.isoformat(),
                )
                for value in values:
                    observed = datetime.fromtimestamp(float(value[0]), tz=UTC)
                    if cursor <= observed <= page_end:
                        rows[observed] = value
                cursor = page_end
        finally:
            await coinbase_client.close()
        candles = [
            BacktestCandle(
                observed_at=datetime.fromtimestamp(float(item[0]), tz=UTC),
                low=Decimal(str(item[1])),
                high=Decimal(str(item[2])),
                open=Decimal(str(item[3])),
                close=Decimal(str(item[4])),
                volume=Decimal(str(item[5])),
            )
            for item in sorted(rows.values(), key=lambda value: value[0])
        ]
        if timeframe == "4h":
            candles = _four_hour_candles(candles)
        return candles[-500:], {
            "provider": "COINBASE",
            "source_version": "exchange-candles-v2",
            "native_granularity_seconds": str(native_seconds),
            "timeframe": timeframe,
        }
    raise ValueError("selected connection does not provide authoritative historical candles")


def _parse_twelve_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _four_hour_candles(candles: list[BacktestCandle]) -> list[BacktestCandle]:
    buckets: dict[int, list[BacktestCandle]] = {}
    for candle in candles:
        bucket = int(candle.observed_at.timestamp()) // 14400 * 14400
        buckets.setdefault(bucket, []).append(candle)
    result = []
    for timestamp, items in sorted(buckets.items()):
        expected = [timestamp + offset * 3600 for offset in range(4)]
        if [int(item.observed_at.timestamp()) for item in items] != expected:
            continue  # Never synthesize a missing hourly observation.
        result.append(
            BacktestCandle(
                observed_at=items[0].observed_at,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum((item.volume for item in items), Decimal(0)),
            )
        )
    return result
