from collections import defaultdict

from modules.analysis.models import RankedMarket, ResearchState


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
