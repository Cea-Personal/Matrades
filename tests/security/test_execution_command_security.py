import pytest

from modules.trading.authority import assert_command_authority
from modules.trading.execution import ExecutionService
from tests.unit.test_execution_service import make_plan, permissions, switches


def test_command_requires_current_kill_switch_epoch() -> None:
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    command = service.create_command(plan, authorization, idempotency_key="security-command-1")
    platform, account = switches()
    platform.safety_epoch = 1
    with pytest.raises(PermissionError, match="epoch"):
        assert_command_authority(
            command, authorization, plan, permissions(plan.account_id), platform, account
        )
