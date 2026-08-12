from fastapi.testclient import TestClient

from traderx_api.main import app


def test_rotation_contract_exposes_only_governed_reactivation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/market-rotation/recommendations" in paths
    assert "/api/v1/market-rotation/instruments/{instrument_id}/reactivation" in paths
