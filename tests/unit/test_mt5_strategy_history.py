from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.market_data import history


async def test_mt5_history_keeps_exact_account_symbol_timeframe_and_window(monkeypatch):
    account_id = uuid4()
    now = datetime.now(UTC)
    snapshot = SimpleNamespace(
        account_id=account_id,
        timeframe="H1",
        sequence=8,
        instruments=[
            SimpleNamespace(
                symbol="XAGUSD.a",
                candles=[
                    SimpleNamespace(
                        observed_at=now - timedelta(hours=index),
                        open=Decimal(30),
                        high=Decimal(32),
                        low=Decimal(29),
                        close=Decimal(31),
                        tick_volume=Decimal(10),
                    )
                    for index in range(20)
                ],
            )
        ],
    )
    closed = []

    class Client:
        def __init__(self, *args):
            pass

        async def market_data(self, requested_account):
            assert requested_account == account_id
            return snapshot

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(history, "Mt5BridgeClient", Client)
    connection = SimpleNamespace(
        secret="fixture",  # noqa: S106
        profile=SimpleNamespace(
            provider=history.ConnectionProvider.MT5_BRIDGE,
            configuration={"bridge_url": "https://fixture.invalid"},
        ),
    )
    args = (connection, "XAGUSD.a", now - timedelta(hours=10), now, "1h")
    candles, source = await history.historical_candles(*args, account_id=account_id)
    assert len(candles) == 11
    assert candles[0].observed_at < candles[-1].observed_at
    assert source["provider"] == "MT5_BRIDGE"
    assert closed == [True]
    snapshot.account_id = uuid4()
    with pytest.raises(ValueError, match="account or timeframe"):
        await history.historical_candles(*args, account_id=account_id)
    snapshot.account_id = account_id
    snapshot.timeframe = "H4"
    with pytest.raises(ValueError, match="account or timeframe"):
        await history.historical_candles(*args, account_id=account_id)
