from __future__ import annotations

from collections.abc import Callable

from modules.market_data.models import (
    ContinuousFuture,
    InstrumentSpecificationVersion,
    VenueInstrument,
)


def chronological_replay(rows: list[dict], evaluator: Callable[[dict], bool]) -> list[bool]:
    ordered = sorted(rows, key=lambda row: row["observed_at"])
    if ordered != rows:
        raise ValueError("replay input must be chronological")
    return [
        evaluator({key: value for key, value in row.items() if key != "future"}) for row in rows
    ]


def require_profile_for_replay(
    listing: VenueInstrument,
    specification: InstrumentSpecificationVersion,
    *,
    continuous: ContinuousFuture | None = None,
) -> None:
    if not listing.executable or listing.continuous_analytical:
        raise ValueError(
            "continuous or non-executable series cannot supply executable replay fills"
        )
    if specification.venue_instrument_id != listing.id or specification.freshness != "VALID":
        raise ValueError("replay specification is not effective for the selected listing")
    if continuous is not None and not continuous.executable:
        # Analytical continuous series may still be used to discover regimes,
        # but must never be silently converted into executable fills.
        raise ValueError("continuous futures are analytical-only in replay")
