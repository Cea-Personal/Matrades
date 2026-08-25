from apps.api.app.routes.research import ResearchRunRequest
from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket, ResearchState


def test_stale_critical_research_degrades():
    assert (
        rank_session(
            [RankedMarket(instrument="BTC", category="CRYPTO", score=1, evidence=[], fresh=False)]
        )[0]
        == ResearchState.DEGRADED
    )


def test_research_run_request_never_accepts_ranked_candidates_from_the_client():
    assert "candidates" not in ResearchRunRequest.model_fields
    assert "account_id" in ResearchRunRequest.model_fields
