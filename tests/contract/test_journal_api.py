from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.journal.model import JournalEntry
from traderx.market_data.model import Instrument
from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_journal_contract_exposes_entries_analytics_and_proposals() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/journal/entries" in paths
    assert "/api/v1/journal/entries/{entry_id}/attachments" in paths
    assert "/api/v1/journal/attachments/{attachment_id}" in paths
    assert "/api/v1/journal/proposals" in paths


def test_protected_journal_screenshot_round_trips_and_analytics_cover_asset_class() -> None:
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
            contract_spec={},
            trading_hours={},
        )
        database.add(instrument)
        database.flush()
        entry = JournalEntry(
            position_id=None,
            paper_run_id=None,
            source_type="DISCRETIONARY",
            instrument_id=instrument.id,
            gross_pnl=Decimal("12"),
            net_pnl=Decimal("10"),
            r_multiple=Decimal("1"),
            evidence={"direction": "LONG", "behavior": "PLAN_FOLLOWED"},
            correction_of_id=None,
            closed_at=datetime(2026, 8, 14, tzinfo=UTC),
        )
        database.add(entry)
        database.flush()
        entry_id = entry.id

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
            json={"email": "journal-owner@example.com", "password": "sufficiently-long-password"},
        )
        password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
        verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=password_headers,
            json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
        )
        headers = {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}

        uploaded = client.post(
            f"/api/v1/journal/entries/{entry_id}/attachments",
            headers=headers,
            files={"file": ("chart.png", b"\x89PNG\r\nprotected-evidence", "image/png")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["protected"] is True
        downloaded = client.get(uploaded.json()["download_path"], headers=headers)
        assert downloaded.content == b"\x89PNG\r\nprotected-evidence"
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert downloaded.headers["x-content-type-options"] == "nosniff"

        analytics = client.get("/api/v1/journal/analytics?dimension=asset_class", headers=headers)
        assert analytics.status_code == 200
        assert analytics.json()["groups"]["FOREX"]["net_pnl"] == "10.000000000000000000"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
