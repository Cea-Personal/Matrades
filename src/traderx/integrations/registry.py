from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider: str
    category: str
    capabilities: frozenset[str]
    official_source_required: bool
    configuration_fields: frozenset[str]
    credential_fields: frozenset[str]


_APPROVED: dict[str, ProviderDefinition] = {
    "MT5_TERMINAL_BRIDGE": ProviderDefinition(
        provider="MT5_TERMINAL_BRIDGE",
        category="BROKER_ACCOUNT_DATA",
        capabilities=frozenset({"ACCOUNT_READ", "INSTRUMENT_READ", "POSITION_READ", "DEAL_READ"}),
        official_source_required=True,
        configuration_fields=frozenset({"account_login", "server"}),
        credential_fields=frozenset(),
    ),
    "WEB_INBOX": ProviderDefinition(
        provider="WEB_INBOX",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=False,
        configuration_fields=frozenset(),
        credential_fields=frozenset(),
    ),
    "EMAIL": ProviderDefinition(
        provider="EMAIL",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=True,
        configuration_fields=frozenset({"sender", "recipient"}),
        credential_fields=frozenset({"api_token"}),
    ),
    "TELEGRAM": ProviderDefinition(
        provider="TELEGRAM",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=True,
        configuration_fields=frozenset({"chat_id"}),
        credential_fields=frozenset({"bot_token"}),
    ),
}


def approved_provider(provider: str) -> ProviderDefinition:
    """Resolve a provider through a deny-by-default capability registry."""

    try:
        return _APPROVED[provider.upper()]
    except KeyError as exc:
        raise ValueError("provider is not approved for TraderX") from exc


def approved_providers(*, category: str | None = None) -> tuple[ProviderDefinition, ...]:
    providers = tuple(_APPROVED.values())
    if category is None:
        return providers
    return tuple(item for item in providers if item.category == category)


def validate_provider_configuration(
    provider: str,
    *,
    requested_capabilities: set[str],
    configuration: dict[str, object],
    credentials: dict[str, object],
    official_source: bool,
) -> ProviderDefinition:
    definition = approved_provider(provider)
    if not requested_capabilities <= definition.capabilities:
        raise ValueError("provider requested a capability outside its approved allowlist")
    if definition.official_source_required and not official_source:
        raise ValueError("this provider requires an approved official source")
    if set(configuration) - definition.configuration_fields:
        raise ValueError("provider configuration contains an unapproved field")
    if set(credentials) != definition.credential_fields:
        raise ValueError("provider credentials do not match the approved write-only fields")
    if any(not str(value).strip() for value in (*configuration.values(), *credentials.values())):
        raise ValueError("provider configuration and credentials cannot contain blank values")
    return definition
