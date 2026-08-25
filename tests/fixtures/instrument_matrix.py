"""Deterministic typed instrument fixtures used by contract and replay tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from modules.market_data.models import (
    FuturesContract,
    FuturesSeries,
    InstrumentSpecificationVersion,
    UnderlyingAsset,
    VenueInstrument,
)
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit

NAMESPACE = UUID("4f47ec1a-5d40-4f0a-89dd-57e5b2f3ab81")
AS_OF = datetime(2026, 1, 2, tzinfo=UTC)


def underlying(asset_class: AssetClass = AssetClass.FOREX) -> UnderlyingAsset:
    return UnderlyingAsset(
        id=uuid5(NAMESPACE, asset_class.value),
        symbol="EURUSD" if asset_class is AssetClass.FOREX else asset_class.value,
        display_name=f"{asset_class.value} fixture",
        asset_class=asset_class,
        base_currency="EUR" if asset_class is AssetClass.FOREX else None,
        quote_currency="USD" if asset_class is AssetClass.FOREX else None,
    )


def listing(
    asset_class: AssetClass = AssetClass.FOREX,
    instrument_type: InstrumentType = InstrumentType.SPOT,
) -> VenueInstrument:
    asset = underlying(asset_class)
    return VenueInstrument(
        id=uuid5(NAMESPACE, f"{asset_class.value}:{instrument_type.value}"),
        underlying_id=asset.id,
        venue="fixture-venue",
        provider="fixture-provider",
        symbol=f"{asset.symbol}_{instrument_type.value}",
        asset_class=asset_class,
        instrument_type=instrument_type,
        continuous_analytical=instrument_type is InstrumentType.FUTURES,
        executable=instrument_type is not InstrumentType.FUTURES,
    )


def specification(
    venue_instrument_id: UUID,
    *,
    quantity_unit: QuantityUnit = QuantityUnit.UNITS,
    effective_from: datetime = AS_OF,
) -> InstrumentSpecificationVersion:
    return InstrumentSpecificationVersion(
        id=uuid5(NAMESPACE, f"spec:{venue_instrument_id}"),
        venue_instrument_id=venue_instrument_id,
        effective_from=effective_from,
        price_currency="USD",
        quantity_unit=quantity_unit,
        contract_multiplier=Decimal("1"),
        tick_size=Decimal("0.0001"),
        quantity_minimum=Decimal("1"),
        quantity_step=Decimal("1"),
        provenance={"provider": "fixture", "cut": "2026-01-02"},
    )


def futures_contract(venue_instrument_id: UUID) -> FuturesContract:
    series = FuturesSeries(
        id=uuid5(NAMESPACE, "series:fixture"),
        underlying_id=underlying(AssetClass.STOCKS).id,
        root_symbol="ES",
        venue="fixture-venue",
    )
    return FuturesContract(
        series_id=series.id,
        venue_instrument_id=venue_instrument_id,
        contract_code="ESH26",
        listed_at=AS_OF - timedelta(days=30),
        last_trade=AS_OF + timedelta(days=60),
    )
