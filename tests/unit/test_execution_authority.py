from decimal import Decimal

import pytest

from modules.trading.authority import assert_command_authority
from modules.trading.execution import ExecutionService
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from modules.trading.ticket import TargetScenario, TradeTicket
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


def test_broker_sized_command_cannot_change_volume_or_loss_cap() -> None:
    plan = make_plan()
    plan.ticket = TradeTicket(
        account_currency="USD",
        requested_risk_limit=Decimal("1000"),
        potential_loss_before_costs=Decimal("500"),
        targets=[TargetScenario(price=Decimal("1.095"), profit_before_costs=Decimal("1000"))],
    )
    service = ExecutionService()
    profile = permissions(plan.account_id)
    platform, account = switches()
    authorization = service.authorize(plan, profile, platform, account)
    command = service.create_command(plan, authorization, idempotency_key="protected-entry-1")
    assert_command_authority(command, authorization, plan, profile, platform, account)
    command.requested_postcondition["quantity"] = "99"
    with pytest.raises(PermissionError, match="broker-sized"):
        assert_command_authority(command, authorization, plan, profile, platform, account)
