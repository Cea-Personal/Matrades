from fastapi.testclient import TestClient

from traderx_api.main import app


def test_paper_and_approval_routes_are_versioned() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/paper/runs" in paths
    assert "/api/v1/approvals/strategies/{strategy_version_id}" in paths
