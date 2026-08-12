from traderx.identity.authorization import Actor, Role
from traderx.integrations.service import ManagedIntegration, configure, set_state


def test_only_allowlisted_read_capabilities_can_be_enabled() -> None:
    actor = Actor(Role.OWNER, "MFA")
    integration = configure(
        actor,
        ManagedIntegration("broker", "DISABLED", frozenset()),
        requested_capabilities={"ACCOUNT_READ"},
    )
    assert set_state(actor, integration, "ENABLED").state == "ENABLED"
