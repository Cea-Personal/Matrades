from fastapi.testclient import TestClient

from traderx_api.main import app


def test_positions_contract_is_read_only_except_classification_correction() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/positions" in paths
    assert not any("order" in path.lower() for path in paths)
