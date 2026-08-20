from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.integrations.crypto import SecretBox
from traderx.integrations.model import CredentialVersion, Integration
from traderx.integrations.registry import (
    approved_provider,
    validate_llm_model_id,
    validate_provider_configuration,
)
from traderx.integrations.service import create_non_broker_integration
from traderx.shared.db import Base, load_model_metadata


def test_catalogue_fixes_provider_endpoints_but_accepts_provider_model_ids() -> None:
    with pytest.raises(ValueError, match="not approved"):
        approved_provider("USER_DEFINED_PROVIDER")
    with pytest.raises(ValueError, match="unapproved field"):
        validate_provider_configuration(
            "COINBASE_EXCHANGE",
            requested_capabilities={"MARKET_DATA_READ"},
            configuration={"base_url": "https://scraped.example"},
            credentials={},
            official_source=True,
        )
    definition = approved_provider("OPENAI_RESPONSES")
    assert definition.permitted_models == {"*"}
    assert definition.fixed_base_url == "https://api.openai.com/v1"
    assert validate_llm_model_id("OPENAI_RESPONSES", "gpt-5.6-luna") == "gpt-5.6-luna"
    assert (
        validate_llm_model_id("ANTHROPIC_MESSAGES", "claude-provider-model-20260820")
        == "claude-provider-model-20260820"
    )
    assert (
        validate_llm_model_id("LITELLM_PROXY", "openrouter/google/gemini-2.5-pro")
        == "openrouter/google/gemini-2.5-pro"
    )
    with pytest.raises(ValueError, match="model identifier"):
        validate_llm_model_id("OPENAI_RESPONSES", "https://models.example/unsafe")
    with pytest.raises(ValueError, match="LLM provider"):
        validate_llm_model_id("COINBASE_EXCHANGE", "gpt-5.6-luna")
    validate_provider_configuration(
        "LITELLM_PROXY",
        requested_capabilities={"LLM_ANALYSIS"},
        configuration={"base_url": "http://litellm:4000/v1"},
        credentials={"virtual_key": "write-only-test-key"},
        official_source=True,
    )
    with pytest.raises(ValueError, match="base URL"):
        validate_provider_configuration(
            "LITELLM_PROXY",
            requested_capabilities={"LLM_ANALYSIS"},
            configuration={"base_url": "http://untrusted-gateway.example/v1"},
            credentials={"virtual_key": "write-only-test-key"},
            official_source=True,
        )


def test_credentials_are_encrypted_and_never_projected_from_the_integration() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    actor = Actor(Role.OWNER, "MFA", uuid4())
    box = SecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    with Session(engine) as database, database.begin():
        integration = create_non_broker_integration(
            database,
            actor,
            provider="LITELLM_PROXY",
            name="Research LiteLLM",
            configuration={"base_url": "http://litellm:4000/v1"},
            credentials={"virtual_key": "plaintext-must-not-persist"},
            requested_capabilities={"LLM_ANALYSIS"},
            official_source=True,
            secret_box=box,
            now=datetime(2026, 8, 14, tzinfo=UTC),
            correlation_id="catalogue-security",
            idempotency_key="catalogue-security-create-0001",
            licensing_accepted=True,
            retention_accepted=True,
        )
        credential = database.scalar(
            select(CredentialVersion).where(CredentialVersion.integration_id == integration.id)
        )
        assert credential is not None
        assert "plaintext-must-not-persist" not in credential.encrypted_value
        assert "plaintext-must-not-persist" not in str(integration.configuration)
        assert database.scalar(select(Integration)).provider == "LITELLM_PROXY"
