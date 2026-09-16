from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from adapters.market_data import history


async def test_four_hour_history_pages_hourly_data_without_duplicate_or_partial_bars(monkeypatch):
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = start + timedelta(hours=400)
    calls = []

    class Client:
        async def candles(self, symbol, granularity, *, start, end):
            first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
            assert symbol == "BTC-USD"
            assert granularity == 3600
            assert (last - first).total_seconds() <= 299 * granularity
            calls.append((first, last))
            return [
                [(first + timedelta(hours=index)).timestamp(), 99, 102, 100, 101, 10]
                for index in range(-1, int((last - first).total_seconds() // 3600) + 1)
            ]

        async def close(self):
            pass

    monkeypatch.setattr(history, "CoinbaseClient", Client)
    connection = SimpleNamespace(
        profile=SimpleNamespace(provider=history.ConnectionProvider.COINBASE)
    )
    candles, source = await history.historical_candles(connection, "BTC-USD", start, end, "4h")
    assert len(calls) == 2
    assert len(candles) == 100
    assert len({item.observed_at for item in candles}) == 100
    assert candles[0].observed_at == start
    assert candles[-1].observed_at == end - timedelta(hours=4)
    assert candles[0].volume == 40
    assert source["native_granularity_seconds"] == "3600"
    hourly = [
        item.model_copy(update={"observed_at": start + timedelta(hours=index)})
        for index, item in enumerate(candles[:3])
    ]
    assert history._four_hour_candles(hourly) == []
