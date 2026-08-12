from fastapi.testclient import TestClient

from traderx_api.main import app


def test_journal_contract_exposes_entries_analytics_and_proposals() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/journal/entries" in paths
    assert "/api/v1/journal/proposals" in paths
