from fastapi.testclient import TestClient

from traderx_api.main import app


def test_strategy_and_validation_operations_are_in_the_contract() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/strategies" in paths
    assert "/api/v1/validation/backtests" in paths
