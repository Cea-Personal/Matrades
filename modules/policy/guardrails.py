from modules.prop_firms.models import GuardrailProfile, PropRule

ALLOWED_SCOPES = {
    "global",
    "account",
    "strategy",
    "exposure",
    "loss",
    "session",
    "event",
    "freshness",
    "trade_count",
}


def update(
    profile: GuardrailProfile,
    scope: str,
    rule: PropRule,
    weakens: bool = False,
    step_up: bool = False,
) -> GuardrailProfile:
    if scope not in ALLOWED_SCOPES:
        raise ValueError("unknown guardrail scope")
    if weakens and not step_up:
        raise PermissionError("step-up required to weaken guardrails")
    return profile.model_copy(
        update={"rules": [*profile.rules, rule], "version": profile.version + 1}
    )
