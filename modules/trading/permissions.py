"""Versioned per-account execution permission transitions."""

from modules.trading.models import ExecutionPermissionProfile


def update_permissions(
    requested: ExecutionPermissionProfile,
    *,
    previous: ExecutionPermissionProfile | None = None,
    step_up_verified: bool,
) -> ExecutionPermissionProfile:
    if not step_up_verified:
        raise PermissionError("execution permission changes require step-up verification")
    version = (previous.version + 1) if previous is not None else 1
    if previous is not None and previous.account_id != requested.account_id:
        raise ValueError("permission account scope cannot change")
    return requested.model_copy(update={"version": version})


__all__ = ["update_permissions"]
