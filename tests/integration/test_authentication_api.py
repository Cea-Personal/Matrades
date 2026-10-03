from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import get_db
from apps.api.app.main import create_app
from apps.api.app.routes import auth as auth_routes
from modules.identity import email_delivery
from modules.identity.service import totp
from packages.shared.config import Settings, get_settings


def test_signup_mfa_login_and_owner_scoped_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        email_delivery,
        "get_settings",
        lambda: get_settings().model_copy(update={"auth_dev_tokens_enabled": True}),
    )
    email = f"owner-{uuid4()}@example.com"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def test_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app(test_engine)
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is True
        signup = client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "correct-horse-battery"},
        )
        assert signup.status_code == 202
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is False
        assert (
            client.post(
                "/api/v1/auth/signup",
                json={
                    "email": "second-owner@example.com",
                    "password": "another-correct-horse-battery",
                },
            ).status_code
            == 409
        )
        assert signup.json()["email_verified"] is False
        assert "verification_token" not in signup.json()
        enrollment = client.post(
            "/api/v1/auth/mfa/enrollments",
            headers={"X-Enrollment-Token": signup.json()["enrollment_token"]},
        )
        assert enrollment.status_code == 201
        recovery_code = enrollment.json()["recovery_codes"][0]
        authenticator_secret = enrollment.json()["secret"]
        confirmation = client.post(
            "/api/v1/auth/mfa/enrollments/confirm",
            json={
                "enrollment_id": enrollment.json()["enrollment_id"],
                "code": totp(authenticator_secret),
            },
        )
        assert confirmation.status_code == 200
        assert client.get("/api/v1/auth/me").json()["email_verification_required"] is False
        created = client.post(
            "/api/v1/configuration/accounts",
            json={
                "name": "Primary",
                "starting_balance": "200000",
                "current_balance": "198000",
                "currency": "USD",
            },
        )
        assert created.status_code == 201
        listed = client.get("/api/v1/configuration/accounts")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["Primary"]
        assert listed.json()[0]["current_balance"] == "198000"
        account_id = created.json()["id"]
        guardrail = client.post(
            "/api/v1/configuration/guardrails",
            json={
                "name": "Risk constitution",
                "verified": True,
                "active": True,
                "rules": [
                    {"kind": "MAX_TOTAL_DRAWDOWN", "value": "16000", "enforcement": "HARD"},
                    {"kind": "MAX_DAILY_LOSS", "value": "4000", "enforcement": "HARD"},
                    {"kind": "MAX_PORTFOLIO_RISK", "value": "3000", "enforcement": "HARD"},
                    {"kind": "MAX_CONCURRENT_TRADES", "value": "3", "enforcement": "HARD"},
                ],
            },
        )
        assert guardrail.status_code == 201
        broker = client.post(
            "/api/v1/trade-management/broker-snapshots",
            json={
                "account_id": account_id,
                "sequence": 1,
                "observed_at": datetime.now(UTC).isoformat(),
                "balance": "198000",
                "equity": "197500",
                "realized_daily_pnl": "-300",
                "positions": [],
                "signature": "authenticated-bridge-channel",
            },
        )
        assert broker.status_code == 202
        proposal = client.post(
            "/api/v1/trade-proposals",
            json={
                "account_id": account_id,
                "candidate": {
                    "instrument": "EURUSD",
                    "direction": "BUY",
                    "market_category": "forex",
                    "requested_size": "5",
                    "entry_price": "1.1",
                    "stop_loss": "1.09",
                    "risk_per_unit": "100",
                    "size_increment": "0.01",
                    "currency_exposures": {"EUR": "1", "USD": "-1"},
                },
                "targets": ["1.12"],
                "invalidation": "Close below structure",
                "strategy_version": "integration-v1",
                "regime": "TREND",
            },
        )
        assert proposal.status_code == 410
        assert "validated Trade Plan" in proposal.json()["detail"]
        assert client.delete("/api/v1/auth/sessions").status_code == 204
        assert client.get("/api/v1/configuration/accounts").status_code == 401

        login = client.post(
            "/api/v1/auth/sessions",
            json={"email": email, "password": "correct-horse-battery"},
        )
        assert login.status_code == 202
        recovered_login = client.post(
            "/api/v1/auth/mfa/challenges",
            json={"challenge_id": login.json()["challenge_id"], "code": recovery_code},
        )
        assert recovered_login.status_code == 200
        step_up = client.post(
            "/api/v1/auth/step-up",
            json={"action_scope": "credential.change", "code": totp(authenticator_secret)},
        )
        assert step_up.status_code == 200
        assert step_up.json()["grant_id"]
        assert client.delete("/api/v1/auth/sessions").status_code == 204

        reused = client.post(
            "/api/v1/auth/sessions",
            json={"email": email, "password": "correct-horse-battery"},
        )
        assert reused.status_code == 202
        assert (
            client.post(
                "/api/v1/auth/mfa/challenges",
                json={"challenge_id": reused.json()["challenge_id"], "code": recovery_code},
            ).status_code
            == 401
        )

        recovery = client.post("/api/v1/auth/password-recovery", json={"email": email})
        assert recovery.status_code == 202
        complete = client.post(
            "/api/v1/auth/password-recovery/complete",
            json={
                "token": recovery.json()["recovery_token"],
                "new_password": "new-correct-horse-battery",
            },
        )
        assert complete.status_code == 200
        assert (
            client.post(
                "/api/v1/auth/sessions",
                json={"email": email, "password": "correct-horse-battery"},
            ).status_code
            == 401
        )
        final_login = client.post(
            "/api/v1/auth/sessions",
            json={"email": email, "password": "new-correct-horse-battery"},
        )
        assert final_login.status_code == 202
        assert (
            client.post(
                "/api/v1/auth/mfa/challenges",
                json={
                    "challenge_id": final_login.json()["challenge_id"],
                    "code": totp(authenticator_secret),
                },
            ).status_code
            == 200
        )


def test_production_signup_sends_link_without_exposing_token_and_closes_signup(
    tmp_path, monkeypatch
) -> None:
    configured = Settings(
        _env_file=None,
        env="production",
        public_app_url="https://matrades.example",
        smtp_host="smtp.example",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password=SecretStr("smtp-password"),
        smtp_from="Matrades <auth@matrades.example>",
        auth_email_verification_enabled=True,
    )
    delivery = {"settings": configured.model_copy(update={"smtp_host": None}), "fail": False}
    monkeypatch.setattr(email_delivery, "get_settings", lambda: delivery["settings"])
    monkeypatch.setattr(auth_routes, "get_settings", lambda: delivery["settings"])
    sent = []

    def send(message, _) -> None:
        if delivery["fail"]:
            raise OSError("mail relay unavailable")
        sent.append(message)

    monkeypatch.setattr(email_delivery, "_send_smtp", send)
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'production-auth.db'}")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def test_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app(test_engine)
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        email = "only-owner@example.com"
        credentials = {"email": email, "password": "correct-horse-battery"}
        assert client.post("/api/v1/auth/signup", json=credentials).status_code == 503
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is True
        delivery["settings"] = configured
        delivery["fail"] = True
        assert client.post("/api/v1/auth/signup", json=credentials).status_code == 503
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is True
        delivery["fail"] = False
        signup = client.post(
            "/api/v1/auth/signup",
            json=credentials,
        )
        assert signup.status_code == 202
        assert "verification_token" not in signup.json()
        assert len(sent) == 1
        link = sent[0].get_content()
        assert "https://matrades.example/auth#verify=" in link
        token = re.search(r"#verify=([A-Za-z0-9_-]+)", link)
        assert token is not None
        assert (
            client.post(
                "/api/v1/auth/signup",
                json={"email": "someone-else@example.com", "password": "correct-horse-battery"},
            ).status_code
            == 409
        )
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is False
        verified = client.post("/api/v1/auth/email-verifications", json={"token": token.group(1)})
        assert verified.status_code == 200
        assert (
            client.post(
                "/api/v1/auth/email-verifications", json={"token": token.group(1)}
            ).status_code
            == 401
        )
        resent = client.post("/api/v1/auth/email-verifications/resend", json={"email": email})
        assert resent.status_code == 202
        assert "verification_token" not in resent.json()
        assert len(sent) == 1  # 60-second resend throttle
        unknown = client.post(
            "/api/v1/auth/email-verifications/resend", json={"email": "unknown@example.com"}
        )
        assert unknown.json() == {"status": "accepted"}
        recovered = client.post("/api/v1/auth/password-recovery", json={"email": email})
        assert recovered.status_code == 202
        assert "recovery_token" not in recovered.json()
        assert "https://matrades.example/auth#recover=" in sent[-1].get_content()


def test_production_owner_setup_code_and_resume_mfa_without_email(tmp_path, monkeypatch) -> None:
    configured = Settings(
        _env_file=None,
        env="production",
        auth_email_verification_enabled=False,
        owner_setup_secret=SecretStr("owner-setup-secret-longer-than-32-characters"),
    )
    settings_holder = {"settings": configured.model_copy(update={"owner_setup_secret": None})}
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings_holder["settings"])
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'setup-auth.db'}")
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def test_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app(test_engine)
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/registration-status").json() == {
            "signup_available": True,
            "email_verification_enabled": False,
            "setup_code_required": True,
        }
        credentials = {"email": "owner@example.com", "password": "correct-horse-battery"}
        assert client.post("/api/v1/auth/signup", json=credentials).status_code == 503
        settings_holder["settings"] = configured
        assert client.post("/api/v1/auth/signup", json=credentials).status_code == 403
        assert (
            client.post(
                "/api/v1/auth/signup", json={**credentials, "setup_code": "wrong-code"}
            ).status_code
            == 403
        )
        assert client.get("/api/v1/auth/registration-status").json()["signup_available"] is True
        signup = client.post(
            "/api/v1/auth/signup",
            json={**credentials, "setup_code": configured.owner_setup_secret.get_secret_value()},
        )
        assert signup.status_code == 202
        assert signup.json()["email_verified"] is False
        assert "enrollment_token" in signup.json()
        assert "verification_token" not in signup.json()
        resumed = client.post("/api/v1/auth/sessions", json=credentials)
        assert resumed.status_code == 202
        assert "enrollment_token" in resumed.json()
        assert (
            client.post(
                "/api/v1/auth/mfa/enrollments",
                headers={"X-Enrollment-Token": resumed.json()["enrollment_token"]},
            ).status_code
            == 201
        )
