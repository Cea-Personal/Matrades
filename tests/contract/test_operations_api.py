from fastapi.testclient import TestClient

from traderx_api.main import app


def test_operations_api_exposes_ui_managed_controls() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    for path in (
        "/api/v1/integrations",
        "/api/v1/jobs",
        "/api/v1/notifications/inbox",
        "/api/v1/operations/audit",
    ):
        assert path in paths
