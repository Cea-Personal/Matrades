import pytest

from modules.trading.authority import assert_command_authority
from modules.trading.execution import ExecutionService
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from tests.unit.test_execution_service import make_plan, permissions, switches


def test_changed_kill_switch_epoch_fences_command():
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    command = service.create_command(plan, authorization, idempotency_key="authority-123")
    with pytest.raises(PermissionError):
        assert_command_authority(
            command,
            authorization,
            plan,
            ExecutionPermissionProfile(account_id=plan.account_id, new_entry=True),
            KillSwitchState(scope="PLATFORM", safety_epoch=authorization.platform_safety_epoch + 1),
            switches()[1],
        )
