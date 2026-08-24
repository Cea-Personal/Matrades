from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket
from modules.identity.service import register


def test_signup_to_hil1_release_journey():
    user = register("user@example.com", "very-long-password")
    state, selected = rank_session(
        [
            RankedMarket(
                instrument="EURUSD", category="FOREX", score=0.9, evidence=["fresh"], fresh=True
            )
        ]
    )
    assert user.email and state == "READY" and selected
