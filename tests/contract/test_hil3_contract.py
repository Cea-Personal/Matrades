from uuid import uuid4

import pytest

from modules.trading.broker_models import ManagementRecommendation, RecommendationAction
from modules.trading.hil3 import Hil3Action, decide
from modules.trading.legacy_compatibility import LegacyWorkflowDisabled


def test_hil3_write_is_disabled_for_autonomous_execution():
    item = ManagementRecommendation(
        trade_id=uuid4(), action=RecommendationAction.MOVE_SL, reason="protect"
    )
    with pytest.raises(LegacyWorkflowDisabled):
        decide(item, Hil3Action.APPROVE, False)
    with pytest.raises(LegacyWorkflowDisabled):
        decide(item, Hil3Action.APPROVE, True)
