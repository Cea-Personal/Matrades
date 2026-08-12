from fastapi.testclient import TestClient

from traderx_api.main import app


def test_openapi_contains_account_and_risk_operations() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/accounts" in paths
    assert "/api/v1/accounts/{account_id}/risk" in paths
