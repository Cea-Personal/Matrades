from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.integrations.model import (
    FreshnessPolicyVersion,
    ProviderCatalogueEntry,
    RetryPolicyVersion,
)


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider: str
    category: str
    capabilities: frozenset[str]
    official_source_required: bool
    configuration_fields: frozenset[str]
    credential_fields: frozenset[str]
    catalogue_revision: str = "2026-08-14.v1"
    adapter_revision: str = "v1"
    lifecycle: str = "APPROVED"
    asset_categories: frozenset[str] = frozenset()
    venues: frozenset[str] = frozenset()
    capability_semantics: tuple[tuple[str, str], ...] = ()
    permitted_models: frozenset[str] = frozenset()
    licensing_notice: str = ""
    retention_posture: str = "NOT_APPLICABLE"
    credential_required: bool = False
    entitlement_required: bool = False
    enabled_by_default: bool = False
    verification_only: bool = False
    fixed_base_url: str | None = None


_APPROVED: dict[str, ProviderDefinition] = {
    "MT5_TERMINAL_BRIDGE": ProviderDefinition(
        provider="MT5_TERMINAL_BRIDGE",
        category="BROKER_ACCOUNT_DATA",
        capabilities=frozenset(
            {"ACCOUNT_READ", "INSTRUMENT_READ", "POSITION_READ", "DEAL_READ", "MARKET_DATA_READ"}
        ),
        official_source_required=True,
        configuration_fields=frozenset({"account_login", "server"}),
        credential_fields=frozenset(),
        capability_semantics=(
            ("ACCOUNT_READ", "AUTHORITATIVE"),
            ("INSTRUMENT_READ", "AUTHORITATIVE"),
            ("MARKET_DATA_READ", "BROKER_PROXY"),
        ),
        enabled_by_default=True,
    ),
    "CME_GROUP": ProviderDefinition(
        provider="CME_GROUP",
        category="MARKET_DATA",
        capabilities=frozenset({"INSTRUMENT_READ", "MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset({"project_id"}),
        credential_fields=frozenset({"api_token"}),
        asset_categories=frozenset({"COMMODITY"}),
        venues=frozenset({"CME", "CBOT", "NYMEX", "COMEX"}),
        capability_semantics=(
            ("TRADED_VOLUME", "ACTUAL"),
            ("OPEN_INTEREST", "ACTUAL"),
            ("TOP_OF_BOOK", "ACTUAL"),
            ("ORDER_BOOK", "ACTUAL"),
        ),
        licensing_notice="CME market-data entitlement and display/retention rights are required.",
        credential_required=True,
        entitlement_required=True,
        fixed_base_url="https://datamine-api.cmegroup.com",
    ),
    "CBOE_FX_SPOT": ProviderDefinition(
        provider="CBOE_FX_SPOT",
        category="MARKET_DATA",
        capabilities=frozenset({"INSTRUMENT_READ", "MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset({"venue"}),
        credential_fields=frozenset({"api_token"}),
        asset_categories=frozenset({"FOREX"}),
        venues=frozenset({"CBOE_FX_SPOT"}),
        capability_semantics=(
            ("TRADED_VOLUME", "ACTUAL"),
            ("TOP_OF_BOOK", "ACTUAL"),
            ("ORDER_BOOK", "ACTUAL"),
        ),
        licensing_notice="Cboe FX data use, display, and retention rights must be verified.",
        credential_required=True,
        entitlement_required=True,
        fixed_base_url="https://fx.cboe.com",
    ),
    "COINBASE_EXCHANGE": ProviderDefinition(
        provider="COINBASE_EXCHANGE",
        category="MARKET_DATA",
        capabilities=frozenset({"INSTRUMENT_READ", "MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset(),
        credential_fields=frozenset(),
        asset_categories=frozenset({"CRYPTO"}),
        venues=frozenset({"COINBASE_EXCHANGE"}),
        capability_semantics=(
            ("TRADED_VOLUME", "ACTUAL"),
            ("TRADES", "ACTUAL"),
            ("CANDLES", "ACTUAL"),
            ("ORDER_BOOK", "ACTUAL"),
        ),
        licensing_notice="Coinbase Exchange market-data terms and retention limits apply.",
        fixed_base_url="https://api.exchange.coinbase.com",
    ),
    "OPENAI_RESPONSES": ProviderDefinition(
        provider="OPENAI_RESPONSES",
        category="LLM",
        capabilities=frozenset({"LLM_ANALYSIS"}),
        official_source_required=True,
        configuration_fields=frozenset(),
        credential_fields=frozenset({"api_key"}),
        catalogue_revision="2026-08-20.v2",
        adapter_revision="openai-responses-v2",
        permitted_models=frozenset({"*"}),
        licensing_notice="Provider retention and pricing posture must be reviewed before use.",
        retention_posture="STANDARD",
        credential_required=True,
        fixed_base_url="https://api.openai.com/v1",
    ),
    "ANTHROPIC_MESSAGES": ProviderDefinition(
        provider="ANTHROPIC_MESSAGES",
        category="LLM",
        capabilities=frozenset({"LLM_ANALYSIS"}),
        official_source_required=True,
        configuration_fields=frozenset(),
        credential_fields=frozenset({"api_key"}),
        catalogue_revision="2026-08-20.v2",
        adapter_revision="anthropic-messages-v2",
        permitted_models=frozenset({"*"}),
        licensing_notice="Provider retention and pricing posture must be reviewed before use.",
        retention_posture="STANDARD",
        credential_required=True,
        fixed_base_url="https://api.anthropic.com/v1",
    ),
    "LITELLM_PROXY": ProviderDefinition(
        provider="LITELLM_PROXY",
        category="LLM",
        capabilities=frozenset({"LLM_ANALYSIS"}),
        official_source_required=False,
        configuration_fields=frozenset({"base_url"}),
        credential_fields=frozenset({"virtual_key"}),
        catalogue_revision="2026-08-20.v1",
        adapter_revision="litellm-openai-compatible-v1",
        permitted_models=frozenset({"*"}),
        licensing_notice="The owner must review the LiteLLM gateway's provider, logging, retention, and spend policies.",
        retention_posture="CONFIGURED_BY_GATEWAY",
        credential_required=True,
    ),
    "CFTC_COT": ProviderDefinition(
        provider="CFTC_COT",
        category="MARKET_DATA",
        capabilities=frozenset({"MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset(),
        credential_fields=frozenset(),
        asset_categories=frozenset({"COMMODITY", "FOREX"}),
        capability_semantics=(("POSITIONING", "ACTUAL"),),
        verification_only=True,
        fixed_base_url="https://publicreporting.cftc.gov",
    ),
    "CME_FX_FUTURES": ProviderDefinition(
        provider="CME_FX_FUTURES",
        category="MARKET_DATA",
        capabilities=frozenset({"MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset({"project_id"}),
        credential_fields=frozenset({"api_token"}),
        asset_categories=frozenset({"FOREX"}),
        capability_semantics=(("TRADED_VOLUME", "ACTUAL"), ("OPEN_INTEREST", "ACTUAL")),
        licensing_notice="CME entitlement and mapping review required; verification only.",
        credential_required=True,
        entitlement_required=True,
        verification_only=True,
        fixed_base_url="https://datamine-api.cmegroup.com",
    ),
    "KRAKEN_SPOT": ProviderDefinition(
        provider="KRAKEN_SPOT",
        category="MARKET_DATA",
        capabilities=frozenset({"INSTRUMENT_READ", "MARKET_DATA_READ"}),
        official_source_required=True,
        configuration_fields=frozenset(),
        credential_fields=frozenset(),
        asset_categories=frozenset({"CRYPTO"}),
        capability_semantics=(("TRADED_VOLUME", "ACTUAL"), ("ORDER_BOOK", "ACTUAL")),
        verification_only=True,
        fixed_base_url="https://api.kraken.com/0/public",
    ),
    "WEB_INBOX": ProviderDefinition(
        provider="WEB_INBOX",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=False,
        configuration_fields=frozenset(),
        credential_fields=frozenset(),
        enabled_by_default=True,
    ),
    "EMAIL": ProviderDefinition(
        provider="EMAIL",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=True,
        configuration_fields=frozenset({"sender", "recipient"}),
        credential_fields=frozenset({"api_token"}),
        credential_required=True,
    ),
    "TELEGRAM": ProviderDefinition(
        provider="TELEGRAM",
        category="NOTIFICATION",
        capabilities=frozenset({"NOTIFICATION_SEND"}),
        official_source_required=True,
        configuration_fields=frozenset({"chat_id"}),
        credential_fields=frozenset({"bot_token"}),
        credential_required=True,
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


def capability_semantics(definition: ProviderDefinition) -> dict[str, str]:
    return dict(definition.capability_semantics)


_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def validate_llm_model_id(provider: str, exact_model_id: str) -> str:
    """Validate a model ID without opening the reviewed provider or endpoint boundary."""

    definition = approved_provider(provider)
    if definition.category != "LLM":
        raise ValueError("model selection requires a reviewed LLM provider")
    normalized = exact_model_id.strip()
    if not _MODEL_ID_PATTERN.fullmatch(normalized) or "://" in normalized or "//" in normalized:
        raise ValueError(
            "model identifier must be 1-128 letters, numbers, dots, underscores, colons, slashes, or hyphens"
        )
    if "*" not in definition.permitted_models and normalized not in definition.permitted_models:
        raise ValueError("model identifier is not permitted for the reviewed provider")
    return normalized


def selectable_models() -> tuple[tuple[str, str], ...]:
    return tuple(
        (definition.provider, model)
        for definition in approved_providers(category="LLM")
        if definition.lifecycle == "APPROVED" and not definition.verification_only
        for model in sorted(definition.permitted_models)
    )


_FRESHNESS_SECONDS: dict[str, dict[str, int]] = {
    "MT5_TERMINAL_BRIDGE": {"QUOTES": 60, "INSTRUMENTS": 60, "CANDLES": 3600},
    "CME_GROUP": {"TRADED_VOLUME": 86400, "OPEN_INTEREST": 86400, "ORDER_BOOK": 60},
    "CBOE_FX_SPOT": {"TRADED_VOLUME": 86400, "TOP_OF_BOOK": 60, "ORDER_BOOK": 60},
    "COINBASE_EXCHANGE": {"TRADES": 60, "CANDLES": 300, "TRADED_VOLUME": 300, "ORDER_BOOK": 60},
    "CFTC_COT": {"POSITIONING": 604800},
    "CME_FX_FUTURES": {"TRADED_VOLUME": 86400, "OPEN_INTEREST": 86400},
    "KRAKEN_SPOT": {"TRADED_VOLUME": 300, "ORDER_BOOK": 60},
}


def seed_provider_catalogue(database: Session, *, effective_at: datetime) -> None:
    """Idempotently persist the code-reviewed catalogue and policy versions."""

    for definition in approved_providers():
        entry = database.scalar(
            select(ProviderCatalogueEntry).where(
                ProviderCatalogueEntry.provider_key == definition.provider,
                ProviderCatalogueEntry.catalogue_revision == definition.catalogue_revision,
            )
        )
        if entry is None:
            database.add(
                ProviderCatalogueEntry(
                    provider_key=definition.provider,
                    catalogue_revision=definition.catalogue_revision,
                    adapter_revision=definition.adapter_revision,
                    category=definition.category,
                    lifecycle=definition.lifecycle,
                    asset_categories=sorted(definition.asset_categories),
                    venues=sorted(definition.venues),
                    capabilities=sorted(definition.capabilities),
                    capability_semantics=capability_semantics(definition),
                    configuration_schema={
                        "allowed_fields": sorted(definition.configuration_fields),
                        "additional_properties": False,
                    },
                    credential_schema={
                        "write_only_fields": sorted(definition.credential_fields),
                        "additional_properties": False,
                    },
                    permitted_models=sorted(definition.permitted_models),
                    licensing_notice=definition.licensing_notice,
                    retention_posture=definition.retention_posture,
                    official_source_required=definition.official_source_required,
                    enabled_by_default=definition.enabled_by_default,
                )
            )
        for capability, maximum_age in _FRESHNESS_SECONDS.get(definition.provider, {}).items():
            if (
                database.scalar(
                    select(FreshnessPolicyVersion.id).where(
                        FreshnessPolicyVersion.provider_key == definition.provider,
                        FreshnessPolicyVersion.capability == capability,
                        FreshnessPolicyVersion.policy_version == "freshness-2026-08-v1",
                    )
                )
                is None
            ):
                database.add(
                    FreshnessPolicyVersion(
                        provider_key=definition.provider,
                        capability=capability,
                        policy_version="freshness-2026-08-v1",
                        maximum_age_seconds=maximum_age,
                        purpose="MARKET_SELECTION",
                        effective_from=effective_at,
                    )
                )
        if (
            database.scalar(
                select(RetryPolicyVersion.id).where(
                    RetryPolicyVersion.provider_key == definition.provider,
                    RetryPolicyVersion.policy_version == "retry-2026-08-v1",
                )
            )
            is None
        ):
            database.add(
                RetryPolicyVersion(
                    provider_key=definition.provider,
                    policy_version="retry-2026-08-v1",
                    maximum_attempts=3,
                    attempt_timeout_seconds=180 if definition.category == "LLM" else 30,
                    overall_timeout_seconds=600 if definition.category == "LLM" else 120,
                    backoff_seconds=[1, 5, 15],
                    honors_retry_after=True,
                    effective_from=effective_at,
                )
            )


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
    if definition.provider == "LITELLM_PROXY":
        _validate_litellm_base_url(str(configuration["base_url"]))
    return definition


def _validate_litellm_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme == "http" and parsed.hostname == "litellm" and not parsed.username:
        return
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "LiteLLM gateway base URL must be HTTPS, or the included http://litellm internal service"
        )
