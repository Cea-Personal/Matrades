from pathlib import Path


def test_security_ui_has_mfa_masking_and_delete_dialog():
    security = Path("apps/web/src/features/security/SecuritySettings.tsx").read_text()
    text = "".join(
        Path(x).read_text()
        for x in (
            "apps/web/src/features/security/SecuritySettings.tsx",
            "apps/web/src/features/configuration/Connections.tsx",
            "apps/web/src/features/configuration/AccountRules.tsx",
        )
    )
    assert "Sensitive-action step-up" not in security
    assert all(
        x in text
        for x in (
            "MFA",
            "••••",
            "Effective limits",
            "step-up",
            "connection.change",
            "hard_rule.change",
        )
    )


def test_connection_ui_exposes_named_data_sources_and_mt5_setup():
    text = Path("apps/web/src/features/configuration/Connections.tsx").read_text()
    dialog = Path("apps/web/src/components/MfaDeleteDialog.tsx").read_text()
    mt5 = Path("apps/web/src/features/connections/MT5Connection.tsx").read_text()
    rules = Path("apps/web/src/features/configuration/AccountRules.tsx").read_text()
    page = Path("apps/web/src/app/connections/page.tsx").read_text()
    assert all(
        value in text
        for value in ("Twelve Data", "Coinbase", "CoinGecko", "FRED", "Calendar", "News")
    )
    assert all(
        value in text + dialog + mt5 + rules + page
        for value in (
            "Bridge URL",
            "Account reference",
            "Test",
            "Account ID",
            "Verify and remove",
        )
    )


def test_configuration_ui_exposes_forex_factory_news_and_mac_wine_guidance():
    text = Path("apps/web/src/features/configuration/Connections.tsx").read_text()
    mt5 = Path("apps/web/src/features/connections/MT5Connection.tsx").read_text()
    assert "Forex Factory" in text
    assert all(
        value in text
        for value in (
            "Forex Factory scraper",
            "Scrape",
            "Scheduled",
            "Save scraper schedule",
            "already archived",
        )
    )
    assert all(value in mt5 for value in ("macOS", "Wine", "Expert Advisor"))


def test_mt5_ea_and_bridge_service_are_shipped():
    ea = Path("bridges/mt5/MatradesMT5BridgeEA.mq5").read_text()
    compose = Path("infra/compose/compose.yaml").read_text()
    readme = Path("bridges/mt5/README.md").read_text()
    assert all(
        value in ea
        for value in ("WebRequest", "/ingest", "InpBridgeSecret", "InpMatradesAccountId")
    )
    assert all(
        value in compose for value in ("mt5-bridge", "8765:8765", "MATRADES_MT5_BRIDGE_SECRET")
    )
    assert all(
        value in readme
        for value in ("MatradesMT5BridgeEA.mq5", "Allow WebRequest", "docker compose")
    )


def test_agent_registry_ui_exposes_test_all_and_execution_feedback():
    text = Path("apps/web/src/features/agents/AgentConfiguration.tsx").read_text()
    assert all(value in text for value in ("Test all logical agents", "execution", "Test"))


def test_research_ui_exposes_per_account_schedule_controls():
    text = Path("apps/web/src/features/research/MarketSelection.tsx").read_text()
    assert all(
        value in text
        for value in ("Per-account research cycle", "Run time", "Save account schedule", "Timezone")
    )
