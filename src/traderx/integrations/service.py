from __future__ import annotations

from dataclasses import dataclass, replace

from traderx.identity.authorization import Actor, Role, require_role

ALLOWED_CAPABILITIES = frozenset(
    {
        "ACCOUNT_READ",
        "INSTRUMENT_READ",
        "POSITION_READ",
        "DEAL_READ",
        "MARKET_DATA_READ",
        "NOTIFICATION_SEND",
    }
)


@dataclass(frozen=True, slots=True)
class ManagedIntegration:
    name: str
    state: str
    capabilities: frozenset[str]
    credential_present: bool = False


def configure(
    actor: Actor, integration: ManagedIntegration, *, requested_capabilities: set[str]
) -> ManagedIntegration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    if not requested_capabilities <= ALLOWED_CAPABILITIES:
        raise ValueError("integration requested a prohibited capability")
    return replace(integration, capabilities=frozenset(requested_capabilities))


def set_state(actor: Actor, integration: ManagedIntegration, target: str) -> ManagedIntegration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.state", require_mfa=True)
    if target not in {"ENABLED", "DISABLED"}:
        raise ValueError("unsupported integration state")
    return replace(integration, state=target)
