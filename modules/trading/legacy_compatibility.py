"""Read-only compatibility boundary for historical HIL/proposal records."""


class LegacyWorkflowDisabled(RuntimeError):
    """Raised when code attempts to create or transition retired HIL records."""


def reject_new_write(workflow: str) -> None:
    raise LegacyWorkflowDisabled(
        f"{workflow} is a read-only legacy record; autonomous Trade Plans are required"
    )


__all__ = ["LegacyWorkflowDisabled", "reject_new_write"]
