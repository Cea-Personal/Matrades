from datetime import timedelta

import pytest

from modules.trading.authorization import authorize_entry
from modules.trading.execution import ExecutionService
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from packages.shared.domain_types import ExecutionAction
from tests.unit.test_execution_service import make_plan


def test_authorization_rereads_permission_and_broker_freshness() -> None:
    plan = make_plan()
    service = ExecutionService()
    permissions = ExecutionPermissionProfile(account_id=plan.account_id, new_entry=True)
    authorization = authorize_entry(
        plan=plan,
        execution=service,
        read_permissions=lambda _: permissions,
        read_kill_switches=lambda _: (
            KillSwitchState(scope="PLATFORM"),
            KillSwitchState(scope="ACCOUNT", account_id=plan.account_id),
        ),
        read_broker_state=lambda _: {"fresh": True, "account_id": str(plan.account_id)},
    )
    assert authorization.action is ExecutionAction.PLACE_ORDER
    assert authorization.expires_at > plan.expires_at - timedelta(minutes=11)


def test_authorization_fails_on_stale_broker_state() -> None:
    plan = make_plan()
    with pytest.raises(PermissionError, match="stale"):
        authorize_entry(
            plan=plan,
            execution=ExecutionService(),
            read_permissions=lambda _: ExecutionPermissionProfile(account_id=plan.account_id),
            read_kill_switches=lambda _: (
                KillSwitchState(scope="PLATFORM"),
                KillSwitchState(scope="ACCOUNT", account_id=plan.account_id),
            ),
            read_broker_state=lambda _: {"fresh": False},
        )
