from __future__ import annotations

from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def _mfa_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def test_broker_integration_api_keeps_credential_write_only_and_requires_discovery_before_binding() -> None:
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
        assert client.get("/api/v1/integrations").status_code == 401
        headers = _mfa_headers(client)
        created = client.post(
            "/api/v1/integrations",
            headers={**headers, "Idempotency-Key": "oanda-integration-request-0001"},
            json={
                "category": "BROKER",
                "provider": "OANDA_V20",
                "configuration": {"environment": "PRACTICE"},
                "credentials": {"personal_access_token": "must-never-appear-in-response"},
            },
        )
        assert created.status_code == 201
        assert created.json()["provider"] == "OANDA_V20"
        assert created.json()["status"] == "DISABLED"
        assert "must-never-appear-in-response" not in created.text
        integration_id = created.json()["id"]

        listed = client.get("/api/v1/integrations", headers=headers)
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == integration_id
        assert client.get(f"/api/v1/integrations/{integration_id}/accounts", headers=headers).json() == []

        rotate = client.put(
            f"/api/v1/integrations/{integration_id}/credentials",
            headers={
                **headers,
                "If-Match": created.headers["etag"],
                "Idempotency-Key": "oanda-credential-rotation-0001",
            },
            json={
                "reason": "Rotate the practice credential safely",
                "confirmation": "CONFIRMED",
                "credentials": {"personal_access_token": "also-not-returned"},
            },
        )
        assert rotate.status_code == 200
        assert "also-not-returned" not in rotate.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
