from collections.abc import Generator
from decimal import Decimal

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.audit.model import AuditEvent
from traderx.market_data.model import Instrument
from traderx.market_research.model import ActiveMarketAssignment, AssignmentState
from traderx.shared.db import Base
from traderx.shared.events import OutboxEvent
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_market_routes_expose_research_and_explicit_activation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/markets/research" in paths
    assert "/api/v1/markets/active/{category}" in paths


def _mfa_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "markets-owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def _candidate_spec(*, available: bool = True, spread: str = "0.0001") -> dict[str, object]:
    closes = [str(Decimal("1.0800") + Decimal(index) / Decimal("10000")) for index in range(61)]
    return {
        "provider_symbol": "EURUSD" if available else "USDZAR",
        "description": "Broker supplied forex instrument",
        "path": "Forex\\Majors" if available else "Forex\\Exotics",
        "bid": "1.0860",
        "ask": str(Decimal("1.0860") + Decimal(spread)),
        "trade_mode": 4 if available else 0,
        "tick_size": "0.00001",
        "tick_value": "1.00",
        "contract_size": "100000",
        "volume_min": "0.01",
        "volume_max": "100",
        "volume_step": "0.01",
        "closes": closes,
        "tick_volumes": [1000 + index for index in range(61)],
    }


def test_authenticated_market_research_and_explicit_activation_are_persisted() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory.begin() as database:
        database.add_all(
            [
                Instrument(
                    symbol="EURUSD",
                    display_name="Euro / US Dollar",
                    category="FOREX",
                    contract_spec=_candidate_spec(),
                    trading_hours={"source": "MT5"},
                ),
                Instrument(
                    symbol="USDZAR",
                    display_name="US Dollar / South African Rand",
                    category="FOREX",
                    contract_spec=_candidate_spec(available=False),
                    trading_hours={"source": "MT5"},
                ),
            ]
        )

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
        started = client.post(
            "/api/v1/markets/research",
            headers={**headers, "Idempotency-Key": "market-research-request-0001"},
            json={"category": "FOREX", "methodology_version": "suitability-v1"},
        )
        assert started.status_code == 202
        assert started.json()["state"] == "COMPLETED"

        report = client.get(f"/api/v1/markets/research/{started.json()['run_id']}", headers=headers)
        assert report.status_code == 200
        candidates = report.json()["candidates"]
        assert [item["symbol"] for item in candidates] == ["EURUSD", "USDZAR"]
        assert candidates[0]["eligible"] is True
        assert candidates[0]["rank"] == 1
        assert candidates[1]["eligible"] is False
        assert "UNSUPPORTED_HOURS" in candidates[1]["exclusions"]

        activated = client.put(
            "/api/v1/markets/active/FOREX",
            headers={
                **headers,
                "If-Match": '"active-FOREX-0"',
                "Idempotency-Key": "active-market-request-0001",
            },
            json={
                "candidate_assessment_id": candidates[0]["id"],
                "replace": False,
                "confirmation": "CONFIRMED",
                "reason": "Approve the highest ranked eligible forex candidate",
            },
        )
        assert activated.status_code == 200
        assert activated.json()["symbol"] == "EURUSD"
        assert activated.json()["state"] == "ACTIVE"

        active = client.get("/api/v1/markets/active", headers=headers)
        assert active.status_code == 200
        assert [(item["category"], item["symbol"]) for item in active.json()["items"]] == [
            ("FOREX", "EURUSD")
        ]

        # Re-running research never changes the approved assignment.
        client.post(
            "/api/v1/markets/research",
            headers={**headers, "Idempotency-Key": "market-research-request-0002"},
            json={"category": "FOREX", "methodology_version": "suitability-v1"},
        )
        active_again = client.get("/api/v1/markets/active", headers=headers)
        assert active_again.json()["items"][0]["symbol"] == "EURUSD"

        deactivated = client.request(
            "DELETE",
            "/api/v1/markets/active/FOREX",
            headers={
                **headers,
                "If-Match": active_again.json()["items"][0]["etag"],
                "Idempotency-Key": "active-market-deactivate-0001",
            },
            json={
                "confirmation": "DEACTIVATE",
                "reason": "Pause forex selection while its evidence is reviewed",
            },
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["state"] == "DEACTIVATED"
        assert client.get("/api/v1/markets/active", headers=headers).json()["items"] == []

        with factory() as database:
            assignment = database.scalar(
                select(ActiveMarketAssignment).where(
                    ActiveMarketAssignment.category == "FOREX"
                )
            )
            assert assignment is not None
            assert assignment.state == AssignmentState.DEACTIVATED
            assert (
                database.scalar(
                    select(AuditEvent).where(AuditEvent.action == "active-market.activate")
                )
                is not None
            )
            assert (
                database.scalar(
                    select(AuditEvent).where(AuditEvent.action == "active-market.deactivate")
                )
                is not None
            )
            assert (
                database.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.event_type
                        == "com.traderx.markets.active-assignment-approved.v1"
                    )
                )
                is not None
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
