from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.accounts.model import TradingAccount
from traderx.integrations.model import Integration
from traderx.market_data.model import Instrument
from traderx.shared.db import Base, load_model_metadata
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def _mfa_headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "research-owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def test_market_research_automation_routes_are_authenticated_and_operational() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as database:
        account = TradingAccount(
            name="Demo",
            mode="DEMO",
            currency="USD",
            starting_balance=Decimal("10000"),
        )
        llm = Integration(
            name="Research LiteLLM",
            category="LLM",
            provider="LITELLM_PROXY",
            state="HEALTHY",
            capabilities=["LLM_ANALYSIS"],
            configuration={"base_url": "http://litellm:4000/v1"},
            official_source=True,
            catalogue_revision="2026-08-14.v1",
            adapter_revision="v1",
            entitlement_status="NOT_REQUIRED",
            retention_posture="CONFIGURED_BY_GATEWAY",
        )
        specialist = Integration(
            name="Coinbase market evidence",
            category="MARKET_DATA",
            provider="COINBASE_EXCHANGE",
            state="HEALTHY",
            capabilities=["MARKET_DATA_READ"],
            configuration={},
            official_source=True,
            catalogue_revision="2026-08-14.v1",
            adapter_revision="v1",
            entitlement_status="NOT_REQUIRED",
        )
        instrument = Instrument(
            symbol="BTCUSD",
            display_name="Bitcoin / US Dollar",
            category="CRYPTO",
            contract_spec={},
            trading_hours={},
        )
        database.add_all([account, llm, specialist, instrument])
        database.flush()
        account_id = str(account.id)
        llm_id = str(llm.id)
        specialist_id = str(specialist.id)
        instrument_id = str(instrument.id)

    def database_override() -> Generator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_database_session] = database_override
    try:
        client = TestClient(app)
        paths = client.get("/api/v1/openapi.json").json()["paths"]
        assert "/api/v1/markets/research/schedule" in paths
        assert "/api/v1/markets/research/model-configuration" in paths
        assert "/api/v1/markets/research/coordinated" in paths
        assert "/api/v1/markets/research/coordinated/{run_id}" in paths
        assert "/api/v1/markets/research/category-runs/{run_id}/llm-analysis/retry" in paths
        assert "/api/v1/markets/instruments/{instrument_id}/mapping" in paths
        assert client.get("/api/v1/markets/research/schedule").status_code == 401

        headers = _mfa_headers(client)
        mapping_payload = {
            "integration_id": specialist_id,
            "provider_symbol": "BTC-USD",
            "venue": "COINBASE_EXCHANGE",
            "mapping_revision": "mapping-v1",
            "reason": "Approve reviewed Coinbase mapping",
        }
        mapping = client.put(
            f"/api/v1/markets/instruments/{instrument_id}/mapping",
            headers={
                **headers,
                "If-Match": f'"instrument-{instrument_id}-1"',
                "Idempotency-Key": "market-symbol-mapping-0001",
            },
            json=mapping_payload,
        )
        assert mapping.status_code == 200
        assert mapping.headers["etag"] == f'"instrument-{instrument_id}-2"'
        mapping_replay = client.put(
            f"/api/v1/markets/instruments/{instrument_id}/mapping",
            headers={
                **headers,
                "If-Match": f'"instrument-{instrument_id}-1"',
                "Idempotency-Key": "market-symbol-mapping-0001",
            },
            json=mapping_payload,
        )
        assert mapping_replay.status_code == 200
        assert mapping_replay.json() == mapping.json()
        conflicting_mapping = client.put(
            f"/api/v1/markets/instruments/{instrument_id}/mapping",
            headers={
                **headers,
                "If-Match": mapping.headers["etag"],
                "Idempotency-Key": "market-symbol-mapping-0001",
            },
            json={**mapping_payload, "provider_symbol": "BTC-USDC"},
        )
        assert conflicting_mapping.status_code == 409

        schedule = client.put(
            "/api/v1/markets/research/schedule",
            headers={
                **headers,
                "If-Match": '"market-research-schedule-0"',
                "Idempotency-Key": "market-schedule-config-0001",
            },
            json={
                "account_id": account_id,
                "interval_seconds": 3600,
                "anchored_start_local": "2026-08-14T09:00:00+00:00",
                "account_timezone": "UTC",
                "enabled": True,
                "reason": "Run research every hour",
            },
        )
        assert schedule.status_code == 200
        assert schedule.json()["next_run_at"]
        assert schedule.json()["enabled"] is True
        schedule_replay = client.put(
            "/api/v1/markets/research/schedule",
            headers={
                **headers,
                "If-Match": '"market-research-schedule-0"',
                "Idempotency-Key": "market-schedule-config-0001",
            },
            json={
                "account_id": account_id,
                "interval_seconds": 3600,
                "anchored_start_local": "2026-08-14T09:00:00+00:00",
                "account_timezone": "UTC",
                "enabled": True,
                "reason": "Run research every hour",
            },
        )
        assert schedule_replay.status_code == 200
        assert schedule_replay.json()["id"] == schedule.json()["id"]

        conflicting_replay = client.put(
            "/api/v1/markets/research/schedule",
            headers={
                **headers,
                "If-Match": schedule.headers["etag"],
                "Idempotency-Key": "market-schedule-config-0001",
            },
            json={
                "account_id": account_id,
                "interval_seconds": 7200,
                "anchored_start_local": "2026-08-14T09:00:00+00:00",
                "account_timezone": "UTC",
                "enabled": True,
                "reason": "Change the recurring interval",
            },
        )
        assert conflicting_replay.status_code == 409

        model = client.put(
            "/api/v1/markets/research/model-configuration",
            headers={
                **headers,
                "If-Match": '"market-research-model-0"',
                "Idempotency-Key": "market-model-config-0001",
            },
            json={
                "llm_integration_id": llm_id,
                "provider_key": "LITELLM_PROXY",
                "exact_model_id": "openrouter/google/gemini-2.5-pro",
                "research_brief": "Focus on macro risk and high-quality volatility context.",
                "reason": "Use the configured LiteLLM research model",
            },
        )
        assert model.status_code == 200
        assert model.json()["applies_to"] == "FUTURE_RUNS_ONLY"
        assert model.json()["exact_model_id"] == "openrouter/google/gemini-2.5-pro"
        assert model.json()["research_brief"] == "Focus on macro risk and high-quality volatility context."

        started = client.post(
            "/api/v1/markets/research/coordinated",
            headers={**headers, "Idempotency-Key": "coordinated-market-run-0001"},
            json={"account_id": account_id, "methodology_version": "market-suitability-v2"},
        )
        assert started.status_code == 202
        report = client.get(
            f"/api/v1/markets/research/coordinated/{started.json()['run_id']}", headers=headers
        )
        assert report.status_code == 200
        assert len(report.json()["categories"]) == 3
        assert report.json()["research_brief"] == "Focus on macro risk and high-quality volatility context."
        assert report.json()["ranking_is_not_activation"] is True
        assert all(
            item["llm_analysis"]["authoritative"] is False for item in report.json()["categories"]
        )
        assert report.json()["model_pin"]["exact_model_id"] == "openrouter/google/gemini-2.5-pro"
        assert report.json()["freshness_policy_manifest"]
        assert all("policy_pins" in item for item in report.json()["categories"])
        assert all("selection_proposal" in item for item in report.json()["categories"])
        history = client.get("/api/v1/markets/research/coordinated", headers=headers)
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == started.json()["run_id"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
