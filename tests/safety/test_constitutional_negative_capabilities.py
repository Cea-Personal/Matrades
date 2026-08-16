import ast
from pathlib import Path

from traderx.integrations.registry import approved_providers
from traderx_api.main import app

ROOTS = (Path("src"), Path("apps/api"), Path("apps/worker"))


def test_production_source_exposes_no_real_money_order_or_scraping_capability() -> None:
    source = "\n".join(path.read_text() for root in ROOTS for path in root.rglob("*.py")).lower()
    forbidden = (
        "submit_order",
        "place_order",
        "create_live_order",
        "modify_order",
        "cancel_order",
        "close_position",
        "selenium",
        "playwright.sync_api",
        "beautifulsoup",
        "scrapy",
    )
    assert not any(term in source for term in forbidden)


def test_api_contract_has_no_order_execution_operation() -> None:
    schema = app.openapi()
    operations = [
        (path, method, str(operation.get("operationId", "")))
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict)
    ]
    forbidden = {"order", "execute", "liquidate", "close-position", "modify-position"}
    assert all(
        not any(term in f"{path} {operation_id}".lower() for term in forbidden)
        for path, _, operation_id in operations
    )


def test_all_approved_capabilities_are_positive_read_or_notification_actions() -> None:
    allowed = {
        "ACCOUNT_READ",
        "INSTRUMENT_READ",
        "POSITION_READ",
        "DEAL_READ",
        "MARKET_DATA_READ",
        "LLM_ANALYSIS",
        "NOTIFICATION_SEND",
    }
    assert approved_providers()
    assert all(provider.capabilities <= allowed for provider in approved_providers())
    assert all(
        provider.official_source_required
        for provider in approved_providers()
        if provider.provider != "WEB_INBOX"
    )


def test_mt5_adapter_imports_no_terminal_trade_method() -> None:
    forbidden = {
        "order_send",
        "order_check",
        "order_calc_margin",
        "order_calc_profit",
        "symbol_select",
    }
    for root in (Path("apps/mt5_bridge"), Path("src/traderx/integrations")):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
                node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            assert not names & forbidden, f"prohibited MT5 capability in {path}"

    ea_source = "\n".join(
        path.read_text(errors="ignore").lower()
        for path in Path("apps/web/public/mt5-bridge").glob("*.mq5")
    )
    assert not any(term.replace("_", "") in ea_source for term in forbidden)


def test_llm_boundary_has_no_tools_account_prompt_or_deterministic_mutation() -> None:
    analysis_source = Path("src/traderx/market_research/llm_analysis.py").read_text().lower()
    schema_source = Path("src/traderx/market_research/llm_schema.py").read_text().lower()
    openai_source = Path(
        "src/traderx/integrations/providers/openai_responses.py"
    ).read_text()
    anthropic_source = Path(
        "src/traderx/integrations/providers/anthropic_messages.py"
    ).read_text()
    assert "deterministic_result_hash =" not in analysis_source
    assert {"balance", "equity", "account_id", "positions", "credential"} <= set(
        schema_source.replace('"', "").replace(",", " ").split()
    )
    assert '"tools": []' in openai_source
    assert '"tools"' not in anthropic_source


def test_provider_and_model_registration_remain_fixed_catalogue_only() -> None:
    providers = approved_providers()
    assert {item.provider for item in providers if not item.verification_only} >= {
        "MT5_TERMINAL_BRIDGE",
        "CME_GROUP",
        "CBOE_FX_SPOT",
        "COINBASE_EXCHANGE",
        "OPENAI_RESPONSES",
        "ANTHROPIC_MESSAGES",
    }
    assert all(
        item.fixed_base_url is None or item.fixed_base_url.startswith("https://")
        for item in providers
    )
    assert all("url" not in item.configuration_fields for item in providers)
