from fastapi.testclient import TestClient

from traderx_api.main import app


def test_opportunity_contract_has_no_execution_operation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/opportunities" in paths
    assert not any("order" in path.lower() for path in paths)
