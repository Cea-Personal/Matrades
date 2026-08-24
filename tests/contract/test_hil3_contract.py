from uuid import uuid4

import pytest

from modules.trading.broker_models import ManagementRecommendation, RecommendationAction
from modules.trading.hil3 import Hil3Action, decide


def test_approval_revalidates_policy_and_never_mutates_broker():
    item = ManagementRecommendation(
        trade_id=uuid4(), action=RecommendationAction.MOVE_SL, reason="protect"
    )
    with pytest.raises(ValueError):
        decide(item, Hil3Action.APPROVE, False)
    assert decide(item, Hil3Action.APPROVE, True)["broker_mutated"] is False
