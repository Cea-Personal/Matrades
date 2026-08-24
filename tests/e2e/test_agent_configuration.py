from pathlib import Path


def test_agent_ui_shows_codex_default_explicit_litellm_and_prompt_chains():
    text = "".join(
        Path(x).read_text()
        for x in (
            "apps/web/src/features/agents/ModelProfiles.tsx",
            "apps/web/src/features/agents/AgentConfiguration.tsx",
            "apps/web/src/features/agents/PromptConfiguration.tsx",
        )
    )
    assert all(
        x in text
        for x in (
            "Codex App Server",
            "explicit assignment",
            "LITELLM_GATEWAY",
            "Agent → Orchestrator → Platform",
        )
    )
