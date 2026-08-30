from decimal import Decimal

from modules.trading.broker_models import (
    ActiveTrade,
    ManagementRecommendation,
    RecommendationAction,
)
from modules.trading.models import ExecutionAction, ExecutionPermissionProfile, KillSwitchState


def monitoring_facts(
    trade: ActiveTrade,
    current_price: Decimal,
    policy_valid: bool,
    bridge_fresh: bool,
    lifecycle_events: list[str] | None = None,
) -> dict[str, object]:
    if not bridge_fresh:
        return {"actionable": False, "reason": "broker state stale"}
    lifecycle_events = lifecycle_events or []
    if lifecycle_events:
        return {
            "actionable": False,
            "reason": "typed instrument lifecycle requires revalidation",
            "revalidation_events": lifecycle_events,
        }
    position = trade.broker_position
    invalidated = (
        position.direction == "BUY"
        and position.stop_loss is not None
        and current_price <= position.stop_loss
    ) or (
        position.direction == "SELL"
        and position.stop_loss is not None
        and current_price >= position.stop_loss
    )
    return {
        "actionable": policy_valid and not invalidated,
        "invalidated": invalidated,
        "pnl": position.pnl,
        "current_price": current_price,
    }


def management_authorization(
    *,
    trade_id,
    action: RecommendationAction,
    permissions: ExecutionPermissionProfile,
    platform_kill: KillSwitchState,
    account_kill: KillSwitchState,
    broker_fresh: bool,
    risk_fresh: bool,
    policy_valid: bool,
) -> ManagementRecommendation:
    """Revalidate every mutable authority input before a management command."""
    if action is RecommendationAction.HOLD:
        return ManagementRecommendation(
            trade_id=trade_id,
            action=action,
            reason="no management trigger",
            requires_authorization=False,
        )
    if not broker_fresh or not risk_fresh:
        reason = "broker or risk snapshot is stale"
    elif platform_kill.active or account_kill.active:
        reason = "platform or account kill switch is active"
    elif not policy_valid:
        reason = "policy or guardrail is not valid"
    else:
        permission_action = {
            RecommendationAction.MOVE_SL: ExecutionAction.SET_OR_CHANGE_STOP_LOSS,
            RecommendationAction.PARTIAL_TP: ExecutionAction.PARTIAL_CLOSE,
            RecommendationAction.EARLY_EXIT: ExecutionAction.FULL_EXIT,
            RecommendationAction.FULL_EXIT: ExecutionAction.FULL_EXIT,
        }.get(action)
        if permission_action is not None and permissions.allows(permission_action):
            reason = "management action passed current authority checks"
        else:
            reason = "management action is disabled for this account"
    return ManagementRecommendation(
        trade_id=trade_id,
        action=action,
        reason=reason,
        requires_authorization=True,
    )
