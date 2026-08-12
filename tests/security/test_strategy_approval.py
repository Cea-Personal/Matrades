from datetime import UTC, datetime, timedelta

import pytest

from traderx.identity.authorization import Actor, Role
from traderx.shared.types import InvalidTransition
from traderx.strategies.approval import ApprovalCommand, approve
from traderx.strategies.approval_model import ApprovalDecision


def test_live_approval_requires_recent_mfa_and_current_evidence() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    with pytest.raises(InvalidTransition):
        approve(
            Actor(Role.OWNER, "MFA"),
            ApprovalCommand(ApprovalDecision.APPROVE_LIVE, False, now, now),
        )
    assert (
        approve(
            Actor(Role.OWNER, "MFA"),
            ApprovalCommand(ApprovalDecision.APPROVE_LIVE, True, now - timedelta(minutes=2), now),
        )
        == ApprovalDecision.APPROVE_LIVE
    )
