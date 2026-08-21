from __future__ import annotations

from datetime import UTC, datetime, timedelta

from traderx.integrations.ports import MarketDataCapability, ProviderObservation, SourceSemantics
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError


class CoinbaseExchangeAdapter:
    provider = "COINBASE_EXCHANGE"
    venue = "COINBASE_EXCHANGE"

    def __init__(self, transport: ProviderHttpTransport | None) -> None:
        self._transport = transport

    def test_connection(self) -> dict[str, object]:
        return {"provider": self.provider, "healthy": bool(self.discover_instruments("CRYPTO"))}

    def capabilities(self) -> dict[str, SourceSemantics]:
        return {
            "TRADES": SourceSemantics.ACTUAL,
            "CANDLES": SourceSemantics.ACTUAL,
            "TRADED_VOLUME": SourceSemantics.ACTUAL,
            "ORDER_BOOK": SourceSemantics.ACTUAL,
        }

    def discover_instruments(self, category: str) -> list[dict[str, object]]:
        if category.upper() not in {"CRYPTO", "CRYPTOCURRENCY"}:
            return []
        return self._records(self._request("/products"))

    def get_instrument_market_snapshot(self, provider_symbol: str) -> dict[str, object]:
        """Read the immutable product rules plus current quote and H1 close history.

        Coinbase spot trades continuously, so these fields are the exchange-native
        counterpart of an MT5 contract specification.  They are used for research
        quality and sizing checks only; this adapter has no order methods.
        """

        now = datetime.now(UTC)
        product = self._request(f"/products/{provider_symbol}")
        ticker = self._request(f"/products/{provider_symbol}/ticker")
        candles = self._request(
            f"/products/{provider_symbol}/candles",
            params={
                "granularity": 3600,
                "start": (now - timedelta(hours=72)).isoformat(),
                "end": now.isoformat(),
            },
        )
        if not isinstance(product, dict) or not isinstance(ticker, dict):
            raise ProviderTransportError("UNKNOWN", "Coinbase returned an invalid product snapshot")
        candle_rows: object = candles if isinstance(candles, list) else candles.get("items", [])
        if not isinstance(candle_rows, list):
            raise ProviderTransportError("UNKNOWN", "Coinbase returned invalid candles")
        return {
            "product": dict(product),
            "ticker": dict(ticker),
            "candles": [dict(row) if isinstance(row, dict) else list(row) if isinstance(row, list) else row for row in candle_rows],
            "received_at": now.isoformat(),
        }

    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        del kind
        payload = self._request(
            f"/products/{provider_symbol}/candles",
            params={
                "granularity": interval,
                "start": start.astimezone(UTC).isoformat(),
                "end": end.astimezone(UTC).isoformat(),
            },
        )
        records = payload if isinstance(payload, list) else payload.get("items", [])
        if not isinstance(records, list):
            raise ProviderTransportError("UNKNOWN", "Coinbase returned invalid candles")
        return [{"values": item} if isinstance(item, list) else dict(item) for item in records]

    def get_observations(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        cursor: str | None = None,
    ) -> list[ProviderObservation]:
        del start, end, cursor
        if capability == MarketDataCapability.ORDER_BOOK:
            path = f"/products/{provider_symbol}/book?level=2"
        elif capability == MarketDataCapability.TRADED_VOLUME:
            path = f"/products/{provider_symbol}/stats"
        elif capability == MarketDataCapability.TRADES:
            path = f"/products/{provider_symbol}/trades"
        else:
            path = f"/products/{provider_symbol}/{capability.value.lower()}"
        payload = self._request(path)
        now = datetime.now(UTC)
        records = [payload] if isinstance(payload, dict) else payload
        return [
            self.normalize_observation(provider_symbol, capability, dict(record), received_at=now)
            for record in records
            if isinstance(record, dict)
        ]

    def normalize_observation(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        payload: dict[str, object],
        *,
        received_at: datetime,
    ) -> ProviderObservation:
        observed = payload.get("time") or payload.get("observed_at")
        parsed = (
            datetime.fromisoformat(str(observed).replace("Z", "+00:00")).astimezone(UTC)
            if observed is not None
            else received_at.astimezone(UTC)
        )
        complete = True
        if capability == MarketDataCapability.ORDER_BOOK:
            complete = bool(payload.get("bids")) and bool(payload.get("asks"))
        return ProviderObservation(
            provider=self.provider,
            provider_symbol=provider_symbol,
            venue=self.venue,
            capability=capability.value,
            semantics=SourceSemantics.ACTUAL,
            observed_at=parsed,
            received_at=received_at.astimezone(UTC),
            sequence=str(payload["sequence"]) if payload.get("sequence") is not None else None,
            provider_event_id=str(payload["trade_id"]) if payload.get("trade_id") is not None else None,
            payload=dict(payload),
            complete=complete,
        )

    def _request(self, path: str, *, params: dict[str, str | int] | None = None) -> dict[str, object] | list[object]:
        if self._transport is None:
            raise ProviderTransportError("UNSUPPORTED", "Coinbase transport is not configured")
        return self._transport.request_json("GET", path, params=params)

    @staticmethod
    def _records(payload: dict[str, object] | list[object]) -> list[dict[str, object]]:
        records: object = payload if isinstance(payload, list) else payload.get("items", [])
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ProviderTransportError("UNKNOWN", "Coinbase returned invalid records")
        return [dict(item) for item in records]
