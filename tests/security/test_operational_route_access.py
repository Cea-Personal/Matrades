from __future__ import annotations

from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.audit.model import AuditEvent
from traderx.identity.model import Role, User
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
    verified = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verified.cookies[SESSION_COOKIE]}"}


def test_operational_routes_require_mfa_session_and_audit_denials() -> None:
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
        for path in (
            "/api/v1/markets/instruments",
            "/api/v1/strategies",
            "/api/v1/paper/runs/example",
            "/api/v1/opportunities",
            "/api/v1/positions",
            "/api/v1/journal/entries",
            "/api/v1/market-rotation/recommendations",
            "/api/v1/jobs",
            "/api/v1/notifications/inbox",
            "/api/v1/operations/audit",
        ):
            assert client.get(path).status_code == 401

        with factory() as database:
            denials = database.scalars(
                select(AuditEvent).where(AuditEvent.outcome == "DENIED")
            ).all()
            assert len(denials) == 10
            assert {event.actor_type for event in denials} == {"ANONYMOUS"}

        headers = _mfa_headers(client)
        assert client.get("/api/v1/markets/instruments", headers=headers).status_code == 200

        with factory() as database:
            owner = database.scalar(select(User).where(User.email == "owner@example.com"))
            assert owner is not None
            owner.role = Role.VIEWER
            database.commit()

        denied = client.post(
            "/api/v1/markets/research",
            headers={**headers, "Idempotency-Key": "market-research-request-0001"},
            json={"category": "FOREX", "methodology_version": "v1"},
        )
        assert denied.status_code == 403
        with factory() as database:
            denial = database.scalar(
                select(AuditEvent)
                .where(AuditEvent.actor_type == "USER", AuditEvent.action == "operational.write")
                .order_by(AuditEvent.occurred_at.desc())
            )
            assert denial is not None
            assert denial.outcome == "DENIED"
            assert denial.actor_role == "VIEWER"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
