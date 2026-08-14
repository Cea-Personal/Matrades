import ast
from pathlib import Path

from traderx.integrations.registry import approved_providers
from traderx_api.main import app

ROOTS = (Path("src"), Path("apps/api"), Path("apps/worker"))


def test_production_source_exposes_no_real_money_order_or_scraping_capability() -> None:
    source = "\n".join(
        path.read_text() for root in ROOTS for path in root.rglob("*.py")
    ).lower()
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
            names = {
                node.id.lower()
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
            } | {
                node.attr.lower()
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
            assert not names & forbidden, f"prohibited MT5 capability in {path}"

    ea_source = "\n".join(
        path.read_text(errors="ignore").lower()
        for path in Path("apps/web/public/mt5-bridge").glob("*.mq5")
    )
    assert not any(term.replace("_", "") in ea_source for term in forbidden)
