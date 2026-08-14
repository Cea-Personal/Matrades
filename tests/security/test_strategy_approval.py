from datetime import UTC, datetime, timedelta

import pytest

from traderx.identity.authorization import Actor, Role
from traderx.shared.types import AuthorizationError, InvalidTransition
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


def test_live_approval_rejects_stale_mfa_and_viewer_authority() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    with pytest.raises(InvalidTransition):
        approve(
            Actor(Role.OWNER, "MFA"),
            ApprovalCommand(
                ApprovalDecision.APPROVE_LIVE,
                True,
                now - timedelta(minutes=6),
                now,
            ),
        )
    with pytest.raises(AuthorizationError):
        approve(
            Actor(Role.VIEWER, "MFA"),
            ApprovalCommand(ApprovalDecision.REJECT, True, now, now),
        )
