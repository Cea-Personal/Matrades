"""Single authority-order guard for all broker command adapters."""

from __future__ import annotations

from modules.risk.models import RiskDecision
from modules.trading.models import (
    ExecutionAction,
    ExecutionAuthorization,
    ExecutionCommand,
    ExecutionPermissionProfile,
    KillSwitchState,
    TradePlan,
    TradePlanState,
)
from packages.shared.domain_types import utc_now


def assert_command_authority(
    command: ExecutionCommand,
    authorization: ExecutionAuthorization,
    plan: TradePlan,
    permissions: ExecutionPermissionProfile,
    platform_kill: KillSwitchState,
    account_kill: KillSwitchState,
) -> None:
    """Fail closed before a broker adapter sees a command."""
    if command.account_id != authorization.account_id or command.account_id != plan.account_id:
        raise PermissionError("command, authorization, and plan account scopes differ")
    if command.authorization_id != authorization.id:
        raise PermissionError("command is not bound to the supplied authorization")
    if authorization.expires_at <= utc_now() or (
        command.action is ExecutionAction.PLACE_ORDER and plan.expires_at <= utc_now()
    ):
        raise PermissionError("authorization or trade plan expired")
    allowed_plan_states = (
        {TradePlanState.AUTHORIZED, TradePlanState.EXECUTION_PENDING}
        if command.action is ExecutionAction.PLACE_ORDER
        else {TradePlanState.ACTIVE, TradePlanState.AUTHORIZED, TradePlanState.EXECUTION_PENDING}
    )
    if plan.state not in allowed_plan_states:
        raise PermissionError("trade plan is not authorized")
    if authorization.action is not command.action:
        raise PermissionError("authorization does not permit the requested action")
    if plan.risk.decision is RiskDecision.HARD_BLOCK:
        raise PermissionError("hard-blocked risk result cannot execute")
    if not permissions.allows(command.action):
        raise PermissionError("action is disabled for the account")
    if platform_kill.active or account_kill.active:
        raise PermissionError("kill switch is active")
    if (
        authorization.platform_safety_epoch != platform_kill.safety_epoch
        or authorization.account_safety_epoch != account_kill.safety_epoch
    ):
        raise PermissionError("kill-switch safety epoch changed")
