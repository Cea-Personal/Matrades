from fastapi.testclient import TestClient

from traderx_api.main import app


def test_health_is_versioned_and_healthy() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-correlation-id"]


def test_openapi_has_versioned_health_operation() -> None:
    document = TestClient(app).get("/api/v1/openapi.json").json()
    assert "/api/v1/health" in document["paths"]
