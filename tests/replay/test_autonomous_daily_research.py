from modules.analysis.daily_research import rank_lanes
from modules.analysis.models import RankedMarket
from modules.research.matrix import ALL_LANES


def test_lane_ranking_is_deterministic_and_same_lane() -> None:
    values = [
        RankedMarket(instrument="EURUSD", category="FOREX", score=0.9, evidence=[], fresh=True)
    ]
    first = rank_lanes(values, list(ALL_LANES))
    assert first == rank_lanes(values, list(ALL_LANES))
    assert first["FOREX:SPOT"][1] is None or first["FOREX:SPOT"][1].instrument == "EURUSD"
