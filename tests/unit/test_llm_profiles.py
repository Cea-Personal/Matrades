from traderx.integrations.llm_profiles import (
    model_prompt_profile,
    prompt_profile_configuration,
    with_owner_system_message,
)


def test_prompt_profile_is_alias_scoped_and_preserves_safety_instruction() -> None:
    configuration = prompt_profile_configuration(
        {"base_url": "http://litellm:4000/v1"},
        alias="research-fast",
        provider_model="openai/gpt-5.6-terra",
        system_message="Focus on the London-session structure.",
        user_message="Explain the market context in plain language.",
    )

    assert model_prompt_profile(configuration, "research-fast") == {
        "provider_model": "openai/gpt-5.6-terra",
        "system_message": "Focus on the London-session structure.",
        "user_message": "Explain the market context in plain language.",
    }
    instruction = with_owner_system_message("TraderX does not place orders.", "Focus on risk.")
    assert instruction.startswith("TraderX does not place orders.")
    assert "Focus on risk." in instruction
