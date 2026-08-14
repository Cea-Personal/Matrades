from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.identity.authentication import SessionManager
from traderx.shared.config import Settings
from traderx.shared.db import Base, load_model_metadata
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_session_csrf_tokens_are_session_bound() -> None:
    manager = SessionManager("pepper")
    first = manager.new_session(datetime(2026, 8, 12, tzinfo=UTC), assurance="MFA")
    second = manager.new_session(datetime(2026, 8, 12, tzinfo=UTC), assurance="MFA")
    assert manager.verify_csrf(first, manager.csrf_token(first))
    assert not manager.verify_csrf(first, manager.csrf_token(second))


def test_cross_site_state_change_is_rejected_before_authentication() -> None:
    response = TestClient(app).post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "cross_origin_request_denied"


def test_session_rotation_defeats_fixation() -> None:
    manager = SessionManager("pepper")
    now = datetime(2026, 8, 12, tzinfo=UTC)
    original = manager.new_session(now, assurance="PASSWORD")
    token, replacement = manager.rotate(original, now, assurance="MFA")
    assert original.revoked_at == now
    assert replacement.token_digest != original.token_digest
    assert manager.verify(token, replacement.token_digest)
    assert not manager.is_active(original, now)


def test_login_abuse_is_generic_rate_limited_and_cannot_bypass_mfa() -> None:
    load_model_metadata()
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
            json={"email": "owner@example.com", "password": "correct-long-password"},
        )
        password_cookie = {
            "Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"
        }
        assert client.get("/api/v1/integrations", headers=password_cookie).status_code == 401

        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "password": "wrong-password-long"},
        )
        known = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password-long"},
        )
        assert unknown.status_code == known.status_code == 401
        assert unknown.json()["detail"] == known.json()["detail"] == "invalid email or password"
        for _ in range(3):
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"email": "owner@example.com", "password": "wrong-password-long"},
                ).status_code
                == 401
            )
        limited = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password-long"},
        )
        assert limited.status_code == 429
        assert limited.json()["code"] == "authentication_rate_limited"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_security_headers_production_secrets_and_ci_scans_are_release_gates() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]

    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://traderx:traderx@localhost/traderx",
        redis_url="redis://localhost:6379/0",
    )
    try:
        settings.validate_startup()
    except ValueError as error:
        assert "TRADERX_SESSION_PEPPER" in str(error)
    else:
        raise AssertionError("production default secrets must be rejected")

    workflow = Path(".github/workflows/security.yml").read_text()
    assert all(tool in workflow for tool in ("pip-audit", "bandit", "npm audit", "action-baseline"))
    assert Path("deploy/security/zap-baseline.conf").is_file()
