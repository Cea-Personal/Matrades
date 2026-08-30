"""Short-lived, fail-closed entry authorization.

Authorization intentionally rereads mutable safety inputs at the boundary.  A
plan or agent may request authorization, but it cannot carry stale permissions,
kill-switch epochs, reservations, or broker freshness into a broker adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from modules.risk.reservations import ReservationBook
from modules.trading.execution import ExecutionService
from modules.trading.models import (
    ExecutionAuthorization,
    ExecutionPermissionProfile,
    KillSwitchState,
    TradePlan,
)


def authorize_entry(
    *,
    plan: TradePlan,
    execution: ExecutionService,
    read_permissions: Callable[[Any], ExecutionPermissionProfile],
    read_kill_switches: Callable[[Any], tuple[KillSwitchState, KillSwitchState]],
    read_broker_state: Callable[[Any], dict[str, Any]],
    reservations: ReservationBook | None = None,
    ttl_seconds: int = 60,
) -> ExecutionAuthorization:
    """Authorize one entry after rereading all mutable authority inputs."""
    if reservations is not None and plan.reservation_id is not None:
        reservation = reservations.active_for(plan.reservation_id, plan.account_id)
        if reservation is None:
            raise PermissionError(
                "risk reservation is missing, expired, or account-scoped incorrectly"
            )
    broker_state = read_broker_state(plan.account_id)
    if not broker_state.get("fresh", True):
        raise PermissionError("authoritative broker state is stale")
    if broker_state.get("account_id") not in (None, str(plan.account_id), plan.account_id):
        raise PermissionError("broker state account scope differs")
    permissions = read_permissions(plan.account_id)
    platform_kill, account_kill = read_kill_switches(plan.account_id)
    return execution.authorize(
        plan,
        permissions,
        platform_kill,
        account_kill,
        ttl_seconds=ttl_seconds,
    )


__all__ = ["authorize_entry"]
