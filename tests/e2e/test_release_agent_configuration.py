from tests.contract.test_agent_registry import (
    test_fixed_registry_defaults_to_codex_and_is_protected,
)
from tests.integration.test_agent_runtime import test_same_runtime_fallback_and_audit
from tests.property.test_prompt_resolution import test_prompt_types_resolve_independently
from tests.security.test_agent_permissions import (
    test_agents_never_receive_broker_or_policy_authority,
)


def test_release_codex_default_and_explicit_alternative_contract():
    test_fixed_registry_defaults_to_codex_and_is_protected()
    test_prompt_types_resolve_independently()
    test_same_runtime_fallback_and_audit()
    test_agents_never_receive_broker_or_policy_authority()
