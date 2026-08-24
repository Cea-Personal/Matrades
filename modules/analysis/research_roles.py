from modules.analysis.models import RankedMarket


def bounded_research(
    instrument: str, category: str, features: dict[str, float], fresh: bool
) -> RankedMarket:
    score = (
        max(0.0, min(1.0, 0.5 + features.get("momentum", 0) - features.get("event_risk", 0) * 0.5))
        if fresh
        else 0.0
    )
    return RankedMarket(
        instrument=instrument,
        category=category,
        score=score,
        evidence=[f"{key}={value:.4f}" for key, value in sorted(features.items())],
        fresh=fresh,
    )
