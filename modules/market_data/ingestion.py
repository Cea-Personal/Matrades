from __future__ import annotations

from datetime import timedelta

from modules.market_data.models import MarketObservation
from packages.shared.domain_types import utc_now


def normalize(
    observation: MarketObservation, max_age: timedelta = timedelta(seconds=30)
) -> MarketObservation:
    if observation.observed_at > observation.received_at:
        raise ValueError("future observations are not permitted")
    if utc_now() - observation.observed_at > max_age:
        raise ValueError("observation is stale")
    if (
        observation.bid is not None
        and observation.ask is not None
        and observation.ask < observation.bid
    ):
        raise ValueError("crossed quote")
    if not observation.provenance:
        raise ValueError("provenance is required")
    return observation
