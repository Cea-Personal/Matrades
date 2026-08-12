from __future__ import annotations

from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.identity import model as identity_model  # noqa: F401
from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_initial_owner_bootstrap_requires_totp_before_dashboard_access() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

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
            json={"email": "owner@example.com", "password": "sufficiently-long-password"},
        )
        assert bootstrap.status_code == 201
        assert bootstrap.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
        password_token = bootstrap.cookies[SESSION_COOKIE]
        password_headers = {"Cookie": f"{SESSION_COOKIE}={password_token}"}

        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
        assert enrollment.status_code == 200
        code = pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()

        verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=password_headers,
            json={"code": code},
        )
        assert verification.status_code == 200
        assert verification.json()["status"] == "AUTHENTICATED"
        assert len(verification.json()["recovery_codes"]) == 8

        mfa_token = verification.cookies[SESSION_COOKIE]
        dashboard = client.get(
            "/api/v1/dashboard", headers={"Cookie": f"{SESSION_COOKIE}={mfa_token}"}
        )
        assert dashboard.status_code == 200

        second_bootstrap = client.post(
            "/api/v1/auth/bootstrap",
            json={"email": "another-owner@example.com", "password": "another-long-password"},
        )
        assert second_bootstrap.status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
