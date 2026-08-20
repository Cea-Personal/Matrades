from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.accounts import model as accounts_model  # noqa: F401
from traderx.identity import model as identity_model  # noqa: F401
from traderx.shared.db import Base
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_openapi_contains_account_and_risk_operations() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/accounts" in paths
    assert "/api/v1/accounts/{account_id}/risk" in paths


def test_owner_can_record_account_and_risk_configuration_but_not_bypass_verification() -> None:
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
        assert client.get("/api/v1/accounts").status_code == 401

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
        mfa_headers = {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}

        created = client.post(
            "/api/v1/accounts",
            headers={**mfa_headers, "Idempotency-Key": "account-setup-request-0001"},
            json={
                "name": "Primary evaluation",
                "currency": "USD",
                "starting_balance": "100000",
                "mode": "LIVE",
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "DRAFT"
        assert created.json()["prop_profile_configured"] is False
        account_id = created.json()["id"]

        prop_profile = client.put(
            f"/api/v1/accounts/{account_id}/prop-profile",
            headers={
                **mfa_headers,
                "If-Match": created.headers["etag"],
                "Idempotency-Key": "prop-profile-request-0001",
            },
            json={
                "daily_loss_limit": "5000",
                "maximum_loss_limit": "10000",
                "trailing_drawdown": False,
                "floating_loss_counts": True,
                "reset_timezone": "UTC",
                "reset_time": "00:00",
                "reason": "Initial external limit configuration",
            },
        )
        assert prop_profile.status_code == 200
        assert prop_profile.json()["prop_profile_configured"] is True

        risk_policy = client.put(
            f"/api/v1/accounts/{account_id}/risk-policy",
            headers={
                **mfa_headers,
                "If-Match": prop_profile.headers["etag"],
                "Idempotency-Key": "risk-policy-request-0001",
            },
            json={
                "maximum_risk_per_trade": "500",
                "maximum_portfolio_risk": "1000",
                "internal_daily_loss_limit": "2000",
                "internal_drawdown_limit": "6000",
                "minimum_prop_buffer": "500",
                "maximum_positions": 2,
                "correlation_limit": "0.75",
                "reason": "Initial internal risk configuration",
            },
        )
        assert risk_policy.status_code == 200
        assert risk_policy.json()["risk_policy_configured"] is True

        dashboard = client.get("/api/v1/dashboard", headers=mfa_headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["account"]["name"] == "Primary evaluation"
        assert dashboard.json()["onboarding"] == {
            "account_configured": True,
            "prop_profile_configured": True,
            "risk_policy_configured": True,
            "account_data_verified": False,
        }
        assert dashboard.json()["risk"]["state"] == "LOCKDOWN"
        assert dashboard.json()["risk"]["reason_codes"] == ["NO_VERIFIED_ACCOUNT_SNAPSHOT"]
        assert dashboard.json()["workflow_progress"] == {
            "healthy_integrations": 0,
            "published_market_research_runs": 0,
            "successful_strategy_versions": 0,
            "active_paper_runs": 0,
        }
        assert dashboard.json()["research_connection_progress"] == [
            {"provider": "TWELVE_DATA", "label": "Twelve Data", "required": False, "complete": False},
            {"provider": "COINBASE_EXCHANGE", "label": "Coinbase Exchange", "required": True, "complete": False},
            {"provider": "LITELLM_PROXY", "label": "LiteLLM Gateway", "required": False, "complete": False},
        ]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
