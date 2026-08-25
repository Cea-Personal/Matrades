from collections import defaultdict

from modules.analysis.models import RankedMarket, ResearchState
from packages.shared.domain_types import ResearchLaneKey


def rank_session(candidates: list[RankedMarket]) -> tuple[ResearchState, list[RankedMarket]]:
    grouped: dict[str, list[RankedMarket]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.category].append(candidate)
    if any(not item.fresh for item in candidates):
        return ResearchState.DEGRADED, []
    selected = [
        max(items, key=lambda item: (item.score, item.instrument))
        for _, items in sorted(grouped.items())
        if items
    ]
    return (ResearchState.READY, selected) if selected else (ResearchState.NO_TRADE, [])


def rank_lanes(
    candidates: list[RankedMarket], requested_lanes: list[ResearchLaneKey]
) -> dict[str, tuple[ResearchState, RankedMarket | None]]:
    """Rank each enabled lane independently; never substitute another type."""
    result: dict[str, tuple[ResearchState, RankedMarket | None]] = {}
    for lane in requested_lanes:
        key = lane.as_string()
        values = [
            item
            for item in candidates
            if item.asset_class is lane.asset_class and item.instrument_type is lane.instrument_type
        ]
        if not values:
            result[key] = (ResearchState.NO_TRADE, None)
            continue
        if any(not item.fresh for item in values):
            result[key] = (ResearchState.DEGRADED, None)
            continue
        result[key] = (
            ResearchState.READY,
            max(values, key=lambda item: (item.score, item.instrument)),
        )
    return result
