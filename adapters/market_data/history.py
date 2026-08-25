"""Historical candle retrieval for deterministic backtesting."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
) -> tuple[list[BacktestCandle], dict[str, str]]:
    if timeframe not in TIMEFRAMES:
        raise ValueError("unsupported timeframe")
    if start_at >= end_at:
        raise ValueError("backtest start must be before end")
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
        try:
            values = await coinbase_client.candles(
                symbol,
                TIMEFRAMES[timeframe][1],
                start=start_at.isoformat(),
                end=end_at.isoformat(),
            )
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
            for item in sorted(values, key=lambda value: value[0])
        ]
        return candles, {"provider": "COINBASE", "source_version": "exchange-candles-v1"}
    raise ValueError("selected connection does not provide authoritative historical candles")


def _parse_twelve_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
