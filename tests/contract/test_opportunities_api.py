from collections.abc import Generator
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.market_data.model import Instrument
from traderx.opportunities.model import Opportunity, OpportunityState
from traderx.opportunities.recommendation_model import Recommendation, RecommendationState
from traderx.shared.db import Base
from traderx.shared.types import utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_opportunity_contract_has_no_execution_operation() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/opportunities" in paths
    assert not any("order" in path.lower() for path in paths)


def test_ranked_opportunity_and_complete_expiring_recommendation_contract() -> None:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory.begin() as database:
        instrument = Instrument(
            symbol="EURUSD",
            display_name="Euro / US Dollar",
            category="FOREX",
            contract_spec={},
            trading_hours={},
        )
        database.add(instrument)
        database.flush()
        opportunity = Opportunity(
            instrument_id=instrument.id,
            strategy_version_id=uuid4(),
            state=OpportunityState.CANDIDATE,
            score=Decimal("0.82"),
            evidence={"score_is_separate_from_risk": True},
            reason_codes=[],
            expires_at=now + timedelta(minutes=15),
            created_at=now,
        )
        database.add(opportunity)
        database.flush()
        recommendation = Recommendation(
            opportunity_id=opportunity.id,
            risk_decision_id=uuid4(),
            state=RecommendationState.ISSUED,
            entry=Decimal("1.08"),
            stop=Decimal("1.075"),
            volume=Decimal("0.5"),
            targets=["1.09"],
            invalidation={"type": "REGIME_CHANGE"},
            reason_trace={"risk_decision": "PASS_REDUCED"},
            expires_at=now + timedelta(minutes=15),
            created_at=now,
        )
        database.add(recommendation)
        database.flush()
        opportunity_id, recommendation_id = str(opportunity.id), recommendation.id

    def database_override() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = database_override
    try:
        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/bootstrap",
            json={"email": "opportunity-owner@example.com", "password": "sufficiently-long-password"},
        )
        password_headers = {"Cookie": f"{SESSION_COOKIE}={login.cookies[SESSION_COOKIE]}"}
        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
        verification = client.post(
            "/api/v1/auth/mfa/enroll/verify",
            headers=password_headers,
            json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
        )
        headers = {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}
        listed = client.get("/api/v1/opportunities", headers=headers)
        assert listed.status_code == 200
        assert Decimal(listed.json()["items"][0]["score"]) > Decimal("0.81")
        detail = client.get(
            f"/api/v1/opportunities/{opportunity_id}/recommendation", headers=headers
        )
        assert detail.json()["manual_execution_only"] is True
        assert {"entry", "stop", "targets", "volume", "invalidation", "reason_trace"}.issubset(
            detail.json()
        )
        with factory.begin() as database:
            actual = database.get(Recommendation, recommendation_id)
            assert actual is not None
            actual.expires_at = utc_now() - timedelta(seconds=1)
        expired = client.get(
            f"/api/v1/opportunities/{opportunity_id}/recommendation", headers=headers
        )
        assert expired.json()["state"] == "EXPIRED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
