from modules.agents.prompts import PromptSet, resolve_prompts


def test_prompt_types_resolve_independently():
    result = resolve_prompts(
        PromptSet(system="agent system"),
        PromptSet(user="orchestrator user"),
        PromptSet(system="platform system", user="platform user"),
    )
    assert result.system == "agent system"
    assert result.user == "orchestrator user"
    assert result.system_source == "agent"
    assert result.user_source == "orchestrator"
