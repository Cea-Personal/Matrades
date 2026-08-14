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


def test_broker_integration_api_exposes_only_the_managed_mt5_enrollment_flow() -> None:
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
        unsupported = client.post(
            "/api/v1/integrations",
            headers={**headers, "Idempotency-Key": "oanda-integration-request-0001"},
            json={
                "category": "BROKER",
                "provider": "OANDA_V20",
                "configuration": {"environment": "PRACTICE"},
                "credentials": {"personal_access_token": "must-never-appear-in-response"},
            },
        )
        assert unsupported.status_code == 405
        assert "must-never-appear-in-response" not in unsupported.text
        assert "OANDA_V20" not in client.get("/api/v1/openapi.json").text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_managed_mt5_enrollment_accepts_outbound_read_only_evidence_without_bridge_fields() -> None:
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
        headers = _mfa_headers(client)
        created = client.post(
            "/api/v1/integrations/mt5/enrollments",
            headers={**headers, "Idempotency-Key": "managed-mt5-enrollment-request-0001"},
            json={"account_login": "123456", "server": "Demo-Server"},
        )
        assert created.status_code == 201
        assert created.json()["provider"] == "MT5_TERMINAL_BRIDGE"
        assert created.json()["name"] == "MT5 Demo-Server 123456"
        assert created.json()["mt5_account_login"] == "123456"
        assert created.json()["mt5_server"] == "Demo-Server"
        assert "bridge_url" not in created.text
        assert "bridge_client_secret" not in created.text
        enrollment = created.json()["enrollment"]
        agent_id = enrollment["agent_id"]
        code = enrollment["code"]

        configuration = client.post(
            f"/api/v1/integrations/mt5/agents/{agent_id}/configuration",
            json={"enrollment_code": code},
        )
        assert configuration.status_code == 200
        assert configuration.json() == {"login": "123456", "server": "Demo-Server"}

        enrolled = client.post(
            f"/api/v1/integrations/mt5/agents/{agent_id}/enroll",
            json={
                "enrollment_code": code,
                "login": "123456",
                "server": "Demo-Server",
                "connected": True,
                "trading_disabled": True,
                "terminal_version": "5.0.1",
            },
        )
        assert enrolled.status_code == 200
        assert "agent_token" in enrolled.json()

        received = client.post(
            f"/api/v1/integrations/mt5/agents/{agent_id}/snapshots",
            headers={"Authorization": f"Bearer {enrolled.json()['agent_token']}"},
            json={
                "login": "123456",
                "server": "Demo-Server",
                "connected": True,
                "trading_disabled": True,
                "terminal_version": "5.0.1",
                "balance": "10000.00",
                "equity": "10005.00",
                "currency": "USD",
                "positions": [],
                "deals": [],
                "instruments": [],
            },
        )
        assert received.status_code == 202
        assert received.json() == {"status": "ACCEPTED"}

        discovered = client.post(
            f"/api/v1/integrations/{created.json()['id']}/test",
            headers={**headers, "Idempotency-Key": "managed-mt5-test-request-0001"},
        )
        assert discovered.status_code == 202
        accounts = client.get(
            f"/api/v1/integrations/{created.json()['id']}/accounts", headers=headers
        )
        assert accounts.status_code == 200
        assert accounts.json()[0]["provider_account_id"] == "123456"

        removed = client.delete(
            f"/api/v1/integrations/{created.json()['id']}",
            headers={**headers, "Idempotency-Key": "managed-mt5-remove-request-0001"},
        )
        assert removed.status_code == 200
        assert removed.json()["status"] == "REMOVED"
        assert removed.json()["unbound_account_count"] == 0
        assert client.get("/api/v1/integrations", headers=headers).json() == []
        assert (
            client.post(
                f"/api/v1/integrations/mt5/agents/{agent_id}/configuration",
                json={"enrollment_code": code},
            ).status_code
            == 409
        )

        reactivated = client.post(
            "/api/v1/integrations/mt5/enrollments",
            headers={**headers, "Idempotency-Key": "managed-mt5-reactivation-request-0001"},
            json={"account_login": "123456", "server": "Demo-Server"},
        )
        assert reactivated.status_code == 201
        assert reactivated.json()["id"] == created.json()["id"]
        assert reactivated.json()["enrollment"]["code"] != code
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
