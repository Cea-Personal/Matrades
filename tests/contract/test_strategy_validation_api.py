from collections.abc import Generator
from decimal import Decimal

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.market_data.model import Instrument
from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_strategy_and_validation_operations_are_in_the_contract() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/strategies" in paths
    assert "/api/v1/validation/backtests" in paths


def _mfa_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "strategy-owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def _definition(entry_value: str = "1.08") -> dict[str, object]:
    return {
        "regime": "TREND",
        "direction": "LONG",
        "timeframes": ["H1"],
        "conditions": [{"field": "close", "operator": ">", "value": entry_value}],
        "filters": [{"field": "spread_bps", "operator": "<", "value": "10"}],
        "stop": {"type": "PERCENT", "value": "0.005"},
        "target": {"type": "RR", "value": "2"},
        "invalidation": {"type": "CLOSE_BELOW_ENTRY"},
        "expiration": {"type": "BARS", "value": 4},
        "risk_fraction": "0.005",
    }


def test_strategy_creation_backtest_validation_and_immutable_edit_work_end_to_end() -> None:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as database:
        instrument = Instrument(
            symbol="EURUSD",
            display_name="Euro / US Dollar",
            category="FOREX",
            contract_spec={
                "bid": "1.0860",
                "ask": "1.0861",
                "closes": [
                    str(Decimal("1.0800") + Decimal(index) / Decimal("10000"))
                    for index in range(61)
                ],
            },
            trading_hours={"source": "MT5"},
        )
        database.add(instrument)
        database.flush()
        instrument_id = str(instrument.id)

    def database_override() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = database_override
    try:
        client = TestClient(app)
        headers = _mfa_headers(client)
        research = client.post(
            "/api/v1/research-jobs",
            headers={**headers, "Idempotency-Key": "strategy-research-request-0001"},
            json={
                "purpose": "ENTRY_PARAMETER_REVIEW",
                "inputs": {"instrument_id": instrument_id},
                "parameters": {"lookback": 60},
            },
        )
        assert research.status_code == 202
        assert len(research.json()["manifest_hash"]) == 64
        research_detail = client.get(
            f"/api/v1/research-jobs/{research.json()['job']['id']}", headers=headers
        )
        assert research_detail.status_code == 200
        assert research_detail.json()["input_manifest"]["parameters"] == {"lookback": 60}

        created = client.post(
            "/api/v1/strategies",
            headers={**headers, "Idempotency-Key": "strategy-create-request-0001"},
            json={
                "name": "H1 trend continuation",
                "instrument_id": instrument_id,
                "definition": _definition(),
                "change_summary": "Initial governed no-code definition",
            },
        )
        assert created.status_code == 201
        version = created.json()["created_version"]
        assert version["sequence"] == 1
        assert version["immutable"] is True
        versions = client.get(
            f"/api/v1/strategies/{created.json()['id']}/versions", headers=headers
        )
        assert [item["sequence"] for item in versions.json()["items"]] == [1]

        backtest = client.post(
            "/api/v1/validation/backtests",
            headers={**headers, "Idempotency-Key": "backtest-request-0001"},
            json={"strategy_version_id": version["id"]},
        )
        assert backtest.status_code == 202
        assert backtest.json()["run"]["state"] == "PASS"
        assert backtest.json()["run"]["metrics"]["same_bar_policy"] == "STOP_FIRST"
        assert "equity_curve" in backtest.json()["run"]["metrics"]

        validation = client.post(
            "/api/v1/validation/runs",
            headers={**headers, "Idempotency-Key": "validation-request-0001"},
            json={
                "strategy_version_id": version["id"],
                "backtest_run_id": backtest.json()["run"]["id"],
                "seed": 17,
            },
        )
        assert validation.status_code == 202
        assert validation.json()["run"]["state"] == "PASS"
        assert validation.json()["run"]["evidence"]["out_of_sample"]["state"] == "PASS"
        assert validation.json()["run"]["evidence"]["portfolio"]["maximum_positions"] == 2

        edited = client.post(
            f"/api/v1/strategies/{created.json()['id']}/versions",
            headers={
                **headers,
                "If-Match": created.headers["etag"],
                "Idempotency-Key": "strategy-version-request-0002",
            },
            json={
                "definition": _definition("1.081"),
                "change_summary": "Raise the entry threshold after review",
            },
        )
        assert edited.status_code == 201
        assert edited.json()["sequence"] == 2
        assert edited.json()["definition_hash"] != version["definition_hash"]
        original = client.get(
            f"/api/v1/strategies/{created.json()['id']}/versions/1", headers=headers
        )
        assert original.json()["definition"]["conditions"][0]["value"] == "1.08"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
