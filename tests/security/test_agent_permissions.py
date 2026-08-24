import pytest

from modules.agents.permissions import PermissionSet


def test_agents_never_receive_broker_or_policy_authority():
    for tool in ("broker.write", "policy.hard.write", "guardrail.reduce"):
        with pytest.raises(ValueError):
            PermissionSet("v1", (tool,))
