"""Reviewed, GET-only Twelve Data adapter.

This adapter deliberately exposes only price/candle continuity data.  It never
claims an exchange venue, order book, or executed-volume authority.
"""

from __future__ import annotations

from datetime import UTC, datetime

from traderx.integrations.ports import MarketDataCapability, ProviderObservation, SourceSemantics
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError


class TwelveDataAdapter:
    provider = "TWELVE_DATA"
    venue = "TWELVE_DATA_COMPOSITE"
    _SUPPORTED_INTERVALS = {
        "1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h", "8h",
        "1day", "1week", "1month",
    }

    def __init__(self, transport: ProviderHttpTransport | None) -> None:
        self._transport = transport

    def test_connection(self) -> dict[str, object]:
        payload = self._request("/price", params={"symbol": "EUR/USD"})
        if not isinstance(payload, dict) or payload.get("price") is None:
            raise ProviderTransportError("UNKNOWN", "Twelve Data price probe was incomplete")
        return {"provider": self.provider, "healthy": True, "venue": self.venue}

    def capabilities(self) -> dict[str, SourceSemantics]:
        return {
            "QUOTES": SourceSemantics.AGGREGATED_PROXY,
            "CANDLES": SourceSemantics.AGGREGATED_PROXY,
            # Some instruments include volume. Consumers must preserve a missing
            # value rather than treating it as zero or venue-authoritative.
            "TRADED_VOLUME": SourceSemantics.AGGREGATED_PROXY,
        }

    def discover_instruments(self, category: str) -> list[dict[str, object]]:
        # The provider's symbol catalogue is not TraderX's market universe.  MT5
        # determines executable Forex/commodity support and Coinbase is crypto's
        # venue authority, so this adapter intentionally does not discover markets.
        del category
        return []

    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        del kind
        if interval not in self._SUPPORTED_INTERVALS:
            raise ValueError("Twelve Data interval is not approved")
        payload = self._request(
            "/time_series",
            params={
                "symbol": provider_symbol,
                "interval": interval,
                "start_date": start.astimezone(UTC).isoformat(),
                "end_date": end.astimezone(UTC).isoformat(),
                "timezone": "UTC",
                "outputsize": 5000,
            },
        )
        if not isinstance(payload, dict):
            raise ProviderTransportError("UNKNOWN", "Twelve Data time series was invalid")
        values = payload.get("values", [])
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise ProviderTransportError("UNKNOWN", "Twelve Data candles were invalid")
        return [dict(item) for item in values]

    def get_observations(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        cursor: str | None = None,
    ) -> list[ProviderObservation]:
        del cursor
        if capability == MarketDataCapability.QUOTES:
            payload = self._request("/price", params={"symbol": provider_symbol})
            return [self.normalize_observation(provider_symbol, capability, self._mapping(payload))]
        if capability == MarketDataCapability.CANDLES:
            if start is None or end is None:
                raise ValueError("Twelve Data candles require a bounded time range")
            rows = self.get_historical_observations(provider_symbol, "CANDLES", "1h", start, end)
            return [self.normalize_observation(provider_symbol, capability, row) for row in rows]
        if capability == MarketDataCapability.TRADED_VOLUME:
            if start is None or end is None:
                raise ValueError("Twelve Data volume requires a bounded time range")
            rows = self.get_historical_observations(provider_symbol, "CANDLES", "1h", start, end)
            return [self.normalize_observation(provider_symbol, capability, row) for row in rows]
        raise ProviderTransportError("UNSUPPORTED", "Twelve Data does not provide this capability")

    def normalize_observation(
        self, provider_symbol: str, capability: MarketDataCapability, payload: dict[str, object]
    ) -> ProviderObservation:
        now = datetime.now(UTC)
        observed = _parse_instant(payload.get("datetime") or payload.get("timestamp"), fallback=now)
        normalized = dict(payload)
        if capability == MarketDataCapability.QUOTES:
            normalized = {"price": payload.get("price")}
        # Missing volume is intentionally represented as absent/null; never zero.
        return ProviderObservation(
            provider=self.provider,
            provider_symbol=provider_symbol,
            venue=self.venue,
            capability=capability.value,
            semantics=SourceSemantics.AGGREGATED_PROXY,
            observed_at=observed,
            received_at=now,
            payload=normalized,
            complete=capability != MarketDataCapability.TRADED_VOLUME or normalized.get("volume") is not None,
        )

    def _request(self, path: str, *, params: dict[str, str | int]) -> dict[str, object] | list[object]:
        if self._transport is None:
            raise ProviderTransportError("UNSUPPORTED", "Twelve Data transport is not configured")
        return self._transport.request_json("GET", path, params=params)

    @staticmethod
    def _mapping(payload: dict[str, object] | list[object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ProviderTransportError("UNKNOWN", "Twelve Data returned an invalid response")
        return payload


def _parse_instant(value: object, *, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=UTC)
    except ValueError:
        return fallback
