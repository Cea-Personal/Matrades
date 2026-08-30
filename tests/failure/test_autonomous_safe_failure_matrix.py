import pytest

from modules.trading.execution import ExecutionService
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from tests.unit.test_execution_service import make_plan


def test_disabled_permission_and_kill_switch_fail_closed() -> None:
    plan = make_plan()
    with pytest.raises(PermissionError):
        ExecutionService().authorize(
            plan,
            ExecutionPermissionProfile(account_id=plan.account_id),
            KillSwitchState(scope="PLATFORM"),
            KillSwitchState(scope="ACCOUNT", account_id=plan.account_id),
        )
    with pytest.raises(PermissionError):
        ExecutionService().authorize(
            plan,
            ExecutionPermissionProfile(account_id=plan.account_id, new_entry=True),
            KillSwitchState(scope="PLATFORM", active=True),
            KillSwitchState(scope="ACCOUNT", account_id=plan.account_id),
        )
