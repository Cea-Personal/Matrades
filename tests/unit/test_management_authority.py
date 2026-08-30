from uuid import uuid4

from modules.trading.broker_models import RecommendationAction
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from modules.trading.monitor import management_authorization


def test_management_action_fails_closed_when_risk_is_stale() -> None:
    result = management_authorization(
        trade_id=uuid4(),
        action=RecommendationAction.FULL_EXIT,
        permissions=ExecutionPermissionProfile(account_id=uuid4(), full_exit=True),
        platform_kill=KillSwitchState(scope="PLATFORM"),
        account_kill=KillSwitchState(scope="ACCOUNT"),
        broker_fresh=True,
        risk_fresh=False,
        policy_valid=True,
    )
    assert result.requires_authorization is True
    assert "stale" in result.reason
