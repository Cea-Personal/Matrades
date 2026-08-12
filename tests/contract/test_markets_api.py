from fastapi.testclient import TestClient

from traderx_api.main import app


def test_market_routes_expose_research_and_explicit_activation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/markets/research" in paths
    assert "/api/v1/markets/active/{category}" in paths
