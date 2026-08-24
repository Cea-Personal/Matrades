from pathlib import Path


def test_security_ui_has_mfa_masking_rules_and_stepup():
    text = "".join(
        Path(x).read_text()
        for x in (
            "apps/web/src/features/security/SecuritySettings.tsx",
            "apps/web/src/features/configuration/Connections.tsx",
            "apps/web/src/features/configuration/AccountRules.tsx",
        )
    )
    assert all(x in text for x in ("MFA", "••••", "Effective limits", "step-up"))
