import pytest

from traderx.identity.authorization import Actor, Role, require_role
from traderx.shared.types import AuthorizationError


def test_viewer_cannot_change_risk() -> None:
    with pytest.raises(AuthorizationError):
        require_role(
            Actor(role=Role.VIEWER, assurance="MFA"), {Role.OWNER, Role.ADMIN}, "risk.change"
        )


def test_owner_can_change_risk() -> None:
    require_role(Actor(role=Role.OWNER, assurance="MFA"), {Role.OWNER}, "risk.change")
