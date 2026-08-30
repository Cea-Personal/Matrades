from apps.api.app.main import create_app


def test_configuration_exposes_targeted_delete_operations() -> None:
    paths = create_app().openapi()["paths"]
    assert "delete" in paths["/api/v1/configuration/accounts/{account_id}"]
    assert "delete" in paths["/api/v1/configuration/connections/{connection_id}"]
    assert "delete" in paths["/api/v1/configuration/guardrails/{rule_id}"]
    assert "delete" in paths["/api/v1/configuration/prop-rulesets/{rule_id}"]


def test_configuration_exposes_forex_factory_as_a_news_source() -> None:
    paths = create_app().openapi()["paths"]
    providers = paths["/api/v1/configuration/connection-providers"]["get"]
    assert providers["operationId"]
    assert "post" in paths["/api/v1/configuration/connections/{connection_id}/forex-factory/scrape"]
    assert "get" in paths["/api/v1/configuration/connections/{connection_id}/forex-factory/archive"]
    assert "get" in paths["/api/v1/configuration/accounts/{account_id}/research-schedule"]
    assert "put" in paths["/api/v1/configuration/accounts/{account_id}/research-schedule"]
    assert "delete" in paths["/api/v1/configuration/accounts/{account_id}/research-schedule"]
    assert "get" in paths["/api/v1/configuration/accounts/{account_id}/forex-factory-schedule"]
    assert "put" in paths["/api/v1/configuration/accounts/{account_id}/forex-factory-schedule"]
    assert "delete" in paths["/api/v1/configuration/accounts/{account_id}/forex-factory-schedule"]
