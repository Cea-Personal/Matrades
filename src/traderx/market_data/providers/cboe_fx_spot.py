from __future__ import annotations

from datetime import UTC, datetime

from traderx.integrations.ports import MarketDataCapability, ProviderObservation, SourceSemantics
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError


class CboeFxSpotAdapter:
    provider = "CBOE_FX_SPOT"
    venue = "CBOE_FX_SPOT"

    def __init__(
        self, transport: ProviderHttpTransport | None, *, entitlement_verified: bool
    ) -> None:
        self._transport = transport
        self._entitlement_verified = entitlement_verified

    def test_connection(self) -> dict[str, object]:
        self._require_entitlement()
        if self._transport is None:
            return {"provider": self.provider, "healthy": True, "fixture": True}
        return {
            "provider": self.provider,
            "healthy": True,
            "payload": self._transport.request_json("GET", "/api/market-data/entitlements"),
        }

    def capabilities(self) -> dict[str, SourceSemantics]:
        return {
            "TRADED_VOLUME": SourceSemantics.ACTUAL,
            "TRADES": SourceSemantics.ACTUAL,
            "TOP_OF_BOOK": SourceSemantics.ACTUAL,
            "ORDER_BOOK": SourceSemantics.ACTUAL,
        }

    def discover_instruments(self, category: str) -> list[dict[str, object]]:
        if category.upper() != "FOREX":
            return []
        return self._records(self._request("/api/market-data/instruments"))

    def get_historical_observations(
        self, provider_symbol: str, kind: str, interval: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        return self._records(
            self._request(
                f"/api/market-data/instruments/{provider_symbol}/history",
                params={
                    "kind": kind,
                    "interval": interval,
                    "start": start.astimezone(UTC).isoformat(),
                    "end": end.astimezone(UTC).isoformat(),
                },
            )
        )

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
        now = datetime.now(UTC)
        return [
            self.normalize_observation(provider_symbol, capability, record, received_at=now)
            for record in self._records(
                self._request(
                    f"/api/market-data/instruments/{provider_symbol}/{capability.value.lower()}"
                )
            )
        ]

    def normalize_observation(
        self,
        provider_symbol: str,
        capability: MarketDataCapability,
        payload: dict[str, object],
        *,
        received_at: datetime,
    ) -> ProviderObservation:
        observed = payload.get("observed_at")
        parsed = (
            datetime.fromisoformat(str(observed).replace("Z", "+00:00")).astimezone(UTC)
            if observed is not None
            else None
        )
        return ProviderObservation(
            provider=self.provider,
            provider_symbol=provider_symbol,
            venue=self.venue,
            capability=capability.value,
            semantics=SourceSemantics.ACTUAL,
            observed_at=parsed,
            received_at=received_at.astimezone(UTC),
            sequence=str(payload["sequence"]) if payload.get("sequence") is not None else None,
            revision=str(payload["revision"]) if payload.get("revision") is not None else None,
            payload=dict(payload),
            complete=True,
        )

    def _request(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> dict[str, object] | list[object]:
        self._require_entitlement()
        if self._transport is None:
            raise ProviderTransportError("UNSUPPORTED", "Cboe FX transport is not configured")
        return self._transport.request_json("GET", path, params=params)

    def _require_entitlement(self) -> None:
        if not self._entitlement_verified:
            raise ProviderTransportError(
                "AUTHORIZATION", "Cboe FX entitlement is required before market evidence can be used"
            )

    @staticmethod
    def _records(payload: dict[str, object] | list[object]) -> list[dict[str, object]]:
        records: object = payload if isinstance(payload, list) else payload.get("items", [])
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ProviderTransportError("UNKNOWN", "Cboe FX returned invalid records")
        return [dict(item) for item in records]
