from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from traderx.identity.authorization import Actor, Role, require_role
from traderx.shared.types import InvalidTransition
from traderx.strategies.approval_model import ApprovalDecision


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    decision: ApprovalDecision
    evidence_current: bool
    mfa_at: datetime | None
    now: datetime


def approve(actor: Actor, command: ApprovalCommand) -> ApprovalDecision:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "strategy.approve", require_mfa=True)
    if command.decision == ApprovalDecision.APPROVE_LIVE:
        if not command.evidence_current:
            raise InvalidTransition("strategy approval needs current evidence")
        if command.mfa_at is None or command.now - command.mfa_at > timedelta(minutes=5):
            raise InvalidTransition("strategy approval needs recent MFA")
    return command.decision
