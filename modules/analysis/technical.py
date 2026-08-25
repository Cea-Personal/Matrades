from __future__ import annotations

from statistics import fmean, pstdev

from modules.market_data.models import InstrumentSpecificationVersion, VenueInstrument


def indicators(closes: list[float]) -> dict[str, float]:
    if len(closes) < 3:
        raise ValueError("at least three point-in-time closes required")
    mean = fmean(closes)
    return {
        "mean": mean,
        "volatility": pstdev(closes),
        "momentum": closes[-1] - closes[0],
        "distance_from_mean": closes[-1] - mean,
    }


def typed_indicators(
    closes: list[float], listing: VenueInstrument, specification: InstrumentSpecificationVersion
) -> dict[str, object]:
    """Attach immutable instrument authority to otherwise pure technical features."""
    return {
        "lane": {
            "asset_class": listing.asset_class.value,
            "instrument_type": listing.instrument_type.value,
        },
        "listing_id": str(listing.id),
        "specification_version_id": str(specification.id),
        "features": indicators(closes),
    }
