from collections.abc import Generator
from datetime import UTC, datetime

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.market_data.model import Instrument, InstrumentAlias
from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_rotation_contract_exposes_only_governed_reactivation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/market-rotation/recommendations" in paths
    assert "/api/v1/market-rotation/history" in paths
    assert "/api/v1/market-rotation/instruments/{instrument_id}/reactivation" in paths


def _headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "rotation-owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def test_reactivation_contract_returns_retained_knowledge_and_never_activates() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as database:
        instrument = Instrument(
            symbol="EURUSD",
            display_name="Euro / US Dollar",
            category="FOREX",
            status="INACTIVE",
            contract_spec={"closes": ["1.08"] * 31},
            trading_hours={"source": "MT5"},
        )
        database.add(instrument)
        database.flush()
        database.add(
            InstrumentAlias(
                instrument_id=instrument.id,
                provider="MT5",
                native_symbol="EURUSD",
                valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        instrument_id = instrument.id

    def database_override() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = database_override
    try:
        client = TestClient(app)
        headers = _headers(client)
        history = client.get("/api/v1/market-rotation/history", headers=headers)
        assert history.status_code == 200
        assert history.json() == {"items": []}

        inspected = client.get(
            f"/api/v1/market-rotation/instruments/{instrument_id}/reactivation",
            headers=headers,
        )
        assert inspected.status_code == 200
        assert inspected.json()["knowledge"]["aliases"] == 1
        assert inspected.json()["ends_in_human_approval"] is True

        requested = client.post(
            f"/api/v1/market-rotation/instruments/{instrument_id}/reactivation",
            headers={**headers, "Idempotency-Key": "reactivation-request-0001"},
        )
        assert requested.status_code == 202
        assert requested.json()["workflow_state"] == "REVALIDATION_REQUIRED"
        assert requested.json()["automatically_activated"] is False
        with factory() as database:
            assert database.get(Instrument, instrument_id).status == "INACTIVE"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
