from datetime import timedelta

from modules.identity.models import Session
from packages.shared.domain_types import utc_now

SENSITIVE_ACTIONS = {
    "credential.change",
    "security.change",
    "broker.change",
    "hard_rule.change",
    "guardrail.reduce",
}


def require_step_up(
    session: Session, action: str, max_age: timedelta = timedelta(minutes=10)
) -> None:
    if action in SENSITIVE_ACTIONS and (
        session.step_up_at is None or utc_now() - session.step_up_at > max_age
    ):
        raise PermissionError("recent MFA step-up required")
