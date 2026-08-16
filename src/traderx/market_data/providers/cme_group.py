from __future__ import annotations

from datetime import UTC, datetime

from traderx.integrations.ports import MarketDataCapability, ProviderObservation, SourceSemantics
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError


class CmeGroupAdapter:
    provider = "CME_GROUP"
    venue = "COMEX"

    def __init__(
        self, transport: ProviderHttpTransport | None, *, entitlement_verified: bool
    ) -> None:
        self._transport = transport
        self._entitlement_verified = entitlement_verified

    def test_connection(self) -> dict[str, object]:
        self._require_entitlement()
        if self._transport is None:
            return {"provider": self.provider, "healthy": True, "fixture": True}
        payload = self._transport.request_json("GET", "/market-data/v1/entitlements")
        return {"provider": self.provider, "healthy": True, "payload": payload}

    def capabilities(self) -> dict[str, SourceSemantics]:
        return {
            "TRADED_VOLUME": SourceSemantics.ACTUAL,
            "OPEN_INTEREST": SourceSemantics.ACTUAL,
            "SETTLEMENT": SourceSemantics.ACTUAL,
            "TOP_OF_BOOK": SourceSemantics.ACTUAL,
            "ORDER_BOOK": SourceSemantics.ACTUAL,
        }

    def discover_instruments(self, category: str) -> list[dict[str, object]]:
        self._require_entitlement()
        if category.upper() != "COMMODITY":
            return []
        payload = self._request("/market-data/v1/instruments")
        return _records(payload)

    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        payload = self._request(
            f"/market-data/v1/instruments/{provider_symbol}/history",
            params={
                "kind": kind,
                "interval": interval,
                "start": start.astimezone(UTC).isoformat(),
                "end": end.astimezone(UTC).isoformat(),
            },
        )
        return _records(payload)

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
        payload = self._request(
            f"/market-data/v1/instruments/{provider_symbol}/{capability.value.lower()}"
        )
        now = datetime.now(UTC)
        return [
            self.normalize_observation(provider_symbol, capability, record, received_at=now)
            for record in _records(payload)
        ]

    def normalize_observation(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        payload: dict[str, object],
        *,
        received_at: datetime,
    ) -> ProviderObservation:
        return ProviderObservation(
            provider=self.provider,
            provider_symbol=provider_symbol,
            venue=self.venue,
            capability=capability.value,
            semantics=SourceSemantics.ACTUAL,
            observed_at=_instant(payload.get("observed_at")),
            received_at=received_at.astimezone(UTC),
            provider_event_id=_optional(payload.get("event_id")),
            sequence=_optional(payload.get("sequence")),
            revision=_optional(payload.get("revision")),
            payload=dict(payload),
            complete=True,
        )

    def _request(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> dict[str, object] | list[object]:
        self._require_entitlement()
        if self._transport is None:
            raise ProviderTransportError("UNSUPPORTED", "CME transport is not configured")
        return self._transport.request_json("GET", path, params=params)

    def _require_entitlement(self) -> None:
        if not self._entitlement_verified:
            raise ProviderTransportError(
                "AUTHORIZATION", "CME entitlement is required before market evidence can be used"
            )


def _records(payload: dict[str, object] | list[object]) -> list[dict[str, object]]:
    records: object = payload if isinstance(payload, list) else payload.get("items", [])
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ProviderTransportError("UNKNOWN", "CME returned an invalid record collection")
    return [dict(item) for item in records]


def _instant(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProviderTransportError("UNKNOWN", "CME returned a timezone-naive timestamp")
    return parsed.astimezone(UTC)


def _optional(value: object) -> str | None:
    return None if value is None else str(value)
