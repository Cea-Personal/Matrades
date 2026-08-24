from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket, ResearchState


def test_stale_critical_research_degrades():
    assert (
        rank_session(
            [RankedMarket(instrument="BTC", category="CRYPTO", score=1, evidence=[], fresh=False)]
        )[0]
        == ResearchState.DEGRADED
    )
