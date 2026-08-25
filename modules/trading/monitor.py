from decimal import Decimal

from modules.trading.broker_models import ActiveTrade


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
