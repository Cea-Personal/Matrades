from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.market_data.model import Instrument
from traderx.shared.db import Base
from traderx.strategies.model import Strategy, StrategyLifecycle, StrategyVersion
from traderx.validation.model import BacktestRun, EvidenceState, ValidationRun
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_paper_and_approval_routes_are_versioned() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/paper/runs" in paths
    assert "/api/v1/approvals/strategies/{strategy_version_id}" in paths
    approval_schema = paths["/api/v1/approvals/strategies/{strategy_version_id}"]["post"]
    request_schema = approval_schema["requestBody"]["content"]["application/json"]["schema"]
    schema_name = request_schema["$ref"].split("/")[-1]
    schema = TestClient(app).get("/api/v1/openapi.json").json()["components"]["schemas"][schema_name]
    assert {"decision", "reason", "paper_run_id", "confirmation"}.issubset(schema["required"])


def test_paper_run_comparison_and_deliberate_rejection_are_persisted() -> None:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 14, tzinfo=UTC)
    with factory.begin() as database:
        instrument = Instrument(
            symbol="EURUSD",
            display_name="Euro / US Dollar",
            category="FOREX",
            contract_spec={
                "bid": "1.08",
                "ask": "1.0801",
                "closes": [str(Decimal("1.08") + Decimal(index) / Decimal("10000")) for index in range(40)],
            },
            trading_hours={},
        )
        database.add(instrument)
        database.flush()
        strategy = Strategy(name="Paper fixture", instrument_id=instrument.id, created_at=now)
        database.add(strategy)
        database.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            sequence=1,
            definition={
                "direction": "LONG",
                "stop": {"value": "0.005"},
                "target": {"value": "2"},
                "risk_fraction": "0.005",
            },
            definition_hash="a" * 64,
            lifecycle=StrategyLifecycle.BACKTEST_PASSED,
            change_summary="Paper fixture version",
            created_at=now,
        )
        database.add(version)
        database.flush()
        backtest = BacktestRun(
            strategy_version_id=version.id,
            manifest_hash="b" * 64,
            execution_model_version="execution-v1",
            metrics={"average_r": "0.5"},
            state=EvidenceState.PASS,
            created_at=now,
        )
        database.add(backtest)
        database.flush()
        validation = ValidationRun(
            strategy_version_id=version.id,
            backtest_run_id=backtest.id,
            manifest_hash="c" * 64,
            seed=17,
            evidence={},
            state=EvidenceState.PASS,
            created_at=now,
        )
        database.add(validation)
        database.flush()
        version_id, validation_id = str(version.id), str(validation.id)

    def database_override() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = database_override
    try:
        client = TestClient(app)
        bootstrap = client.post(
            "/api/v1/auth/bootstrap",
            json={"email": "paper-owner@example.com", "password": "sufficiently-long-password"},
        )
        password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
        verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=password_headers,
            json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
        )
        headers = {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}
        started = client.post(
            "/api/v1/paper/runs",
            headers={**headers, "Idempotency-Key": "paper-run-request-0001"},
            json={
                "strategy_version_id": version_id,
                "validation_run_id": validation_id,
                "evidence_manifest_hash": "c" * 64,
            },
        )
        assert started.status_code == 202
        run = started.json()["run"]
        assert run["comparison"]["historical_manifest_hash"] == "b" * 64
        assert run["history"]
        assert run["state"] == "REVIEW_REQUIRED"
        strategy_payload = client.get("/api/v1/strategies", headers=headers).json()["items"][0]
        version_etag = strategy_payload["versions"][0]["etag"]
        rejected = client.post(
            f"/api/v1/approvals/strategies/{version_id}",
            headers={
                **headers,
                "If-Match": version_etag,
                "Idempotency-Key": "paper-reject-request-0001",
            },
            json={
                "paper_run_id": run["id"],
                "decision": "REJECT",
                "reason": "Paper evidence remains below the required threshold",
                "confirmation": "CONFIRMED",
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["decision"] == "REJECT"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
