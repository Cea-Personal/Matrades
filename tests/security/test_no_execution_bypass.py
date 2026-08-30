import pytest

from modules.trading.authority import assert_command_authority
from modules.trading.execution import ExecutionService
from modules.trading.models import ExecutionPermissionProfile
from tests.unit.test_execution_service import make_plan, permissions, switches


def test_disabled_permission_reaches_no_broker_authority():
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    command = service.create_command(plan, authorization, idempotency_key="bypass-1234")
    with pytest.raises(PermissionError):
        assert_command_authority(
            command,
            authorization,
            plan,
            ExecutionPermissionProfile(account_id=plan.account_id),
            switches()[0],
            switches()[1],
        )
