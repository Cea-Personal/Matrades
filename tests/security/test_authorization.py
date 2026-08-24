from uuid import uuid4

import pytest

from modules.identity.authorization import Actor, Role


def test_owner_isolation_and_role_denial():
    viewer = Actor(uuid4(), uuid4(), Role.VIEWER)
    with pytest.raises(PermissionError):
        viewer.require(Role.OWNER)
