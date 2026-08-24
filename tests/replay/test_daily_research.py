from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket, ResearchState


def test_one_per_category_and_deterministic():
    items = [
        RankedMarket(instrument="B", category="FOREX", score=0.5, evidence=[], fresh=True),
        RankedMarket(instrument="A", category="FOREX", score=0.8, evidence=[], fresh=True),
        RankedMarket(instrument="XAU", category="METAL", score=0.7, evidence=[], fresh=True),
    ]
    first = rank_session(items)
    assert first == rank_session(items)
    assert first[0] == ResearchState.READY
    assert [x.instrument for x in first[1]] == ["A", "XAU"]
