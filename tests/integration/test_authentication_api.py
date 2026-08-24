from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import get_db
from apps.api.app.main import create_app
from modules.identity.service import totp


def test_signup_verification_mfa_login_and_owner_scoped_api(tmp_path) -> None:
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
        signup = client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "correct-horse-battery"},
        )
        assert signup.status_code == 202
        verification = client.post(
            "/api/v1/auth/email-verifications",
            json={"token": signup.json()["verification_token"]},
        )
        assert verification.status_code == 200
        enrollment = client.post(
            "/api/v1/auth/mfa/enrollments",
            headers={"X-Enrollment-Token": verification.json()["enrollment_token"]},
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
        created = client.post(
            "/api/v1/configuration/accounts",
            json={"name": "Primary", "starting_balance": "200000", "currency": "USD"},
        )
        assert created.status_code == 201
        listed = client.get("/api/v1/configuration/accounts")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["Primary"]
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
        assert proposal.status_code == 201
        assert proposal.json()["risk"]["snapshot"]["account_equity"] == "197500"
        assert proposal.json()["risk"]["snapshot"]["source"] == "MT5_READ_ONLY_BRIDGE"
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
        assert client.post(
            "/api/v1/auth/mfa/challenges",
            json={"challenge_id": reused.json()["challenge_id"], "code": recovery_code},
        ).status_code == 401

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
        assert client.post(
            "/api/v1/auth/sessions",
            json={"email": email, "password": "correct-horse-battery"},
        ).status_code == 401
        final_login = client.post(
            "/api/v1/auth/sessions",
            json={"email": email, "password": "new-correct-horse-battery"},
        )
        assert final_login.status_code == 202
        assert client.post(
            "/api/v1/auth/mfa/challenges",
            json={
                "challenge_id": final_login.json()["challenge_id"],
                "code": totp(authenticator_secret),
            },
        ).status_code == 200
