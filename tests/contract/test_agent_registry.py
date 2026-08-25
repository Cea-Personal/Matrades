import pytest

from modules.agents.models import RuntimeType
from modules.agents.registry import REQUIRED_AGENT_IDS, seed


def test_fixed_registry_defaults_to_codex_and_is_protected():
    registry = seed()
    assert len(REQUIRED_AGENT_IDS) >= 16
    assert "stocks_research" in REQUIRED_AGENT_IDS
    assert all(x.runtime == RuntimeType.CODEX_APP_SERVER for x in registry.all())
    with pytest.raises(ValueError):
        registry.remove("orchestrator")
