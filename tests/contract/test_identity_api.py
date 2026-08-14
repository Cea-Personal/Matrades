from __future__ import annotations

from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.identity import model as identity_model  # noqa: F401
from traderx.identity.authentication import PasswordRecoveryManager
from traderx.identity.model import RecoveryChallenge, User
from traderx.shared.db import Base
from traderx.shared.types import utc_now
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
        assert f"{SESSION_COOKIE}=" in bootstrap.headers["set-cookie"]
        assert "Secure" in bootstrap.headers["set-cookie"]
        assert "HttpOnly" in bootstrap.headers["set-cookie"]
        assert "SameSite=strict" in bootstrap.headers["set-cookie"]
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


def test_recovery_code_reset_requires_fresh_totp_enrollment() -> None:
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
        password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
        code = pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()
        verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=password_headers,
            json={"code": code},
        )
        reset_token, reset_view = PasswordRecoveryManager("development-only-change-me").issue(
            utc_now()
        )
        session = factory()
        try:
            owner = session.query(User).filter_by(email="owner@example.com").one()
            session.add(
                RecoveryChallenge(
                    user_id=owner.id,
                    token_digest=reset_view.token_digest,
                    expires_at=reset_view.expires_at,
                )
            )
            session.commit()
        finally:
            session.close()

        completed = client.post(
            "/api/v1/auth/password-reset/complete",
            json={
                "reset_token": reset_token,
                "new_password": "a-new-sufficiently-long-password",
                "proof": {"recovery_code": verification.json()["recovery_codes"][1]},
            },
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
        old_password = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "sufficiently-long-password"},
        )
        assert old_password.status_code == 401
        new_password = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "a-new-sufficiently-long-password"},
        )
        assert new_password.status_code == 200
        assert new_password.json()["status"] == "MFA_ENROLLMENT_REQUIRED"

        new_password_headers = {
            "Cookie": f"{SESSION_COOKIE}={new_password.cookies[SESSION_COOKIE]}"
        }
        fresh_enrollment = client.post("/api/v1/auth/mfa/enroll", headers=new_password_headers)
        fresh_code = pyotp.parse_uri(fresh_enrollment.json()["provisioning_uri"]).now()
        fresh_verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=new_password_headers,
            json={"code": fresh_code},
        )
        recovery_code = fresh_verification.json()["recovery_codes"][0]
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "a-new-sufficiently-long-password"},
        )
        recovered = client.post(
            "/api/v1/auth/mfa/recovery",
            headers={"Cookie": f"{SESSION_COOKIE}={login.cookies[SESSION_COOKIE]}"},
            json={"recovery_code": recovery_code},
        )
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
        assert (
            client.post(
                "/api/v1/auth/mfa/recovery",
                headers={"Cookie": f"{SESSION_COOKIE}={recovered.cookies[SESSION_COOKIE]}"},
                json={"recovery_code": recovery_code},
            ).status_code
            == 401
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
