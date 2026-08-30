"""Monotonic platform and account safety epochs."""


from modules.trading.models import KillSwitchState


def update_kill_switch(
    requested: KillSwitchState,
    *,
    previous: KillSwitchState | None = None,
    step_up_verified: bool,
    health_verified: bool = False,
) -> KillSwitchState:
    if not step_up_verified:
        raise PermissionError("kill-switch changes require step-up verification")
    if previous is not None and previous.scope != requested.scope:
        raise ValueError("kill-switch scope cannot change")
    if requested.scope == "ACCOUNT" and requested.account_id is None:
        raise ValueError("account kill switch requires account scope")
    if previous is not None and previous.active and not requested.active and not health_verified:
        raise PermissionError("kill-switch deactivation requires fresh broker/account health")
    return requested.model_copy(
        update={"safety_epoch": (previous.safety_epoch + 1) if previous else 1}
    )


__all__ = ["update_kill_switch"]
