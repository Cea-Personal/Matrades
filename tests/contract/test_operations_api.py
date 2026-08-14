from collections.abc import Generator
from datetime import UTC, datetime

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.db import Base, load_model_metadata
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def test_operations_api_exposes_ui_managed_controls() -> None:
    paths = TestClient(app).get("/api/v1/openapi.json").json()["paths"]
    for path in (
        "/api/v1/integrations",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}/events",
        "/api/v1/notifications/inbox",
        "/api/v1/notifications/preferences/{channel}",
        "/api/v1/operations/health",
        "/api/v1/operations/audit",
    ):
        assert path in paths


def _headers(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "operations-owner@example.com", "password": "sufficiently-long-password"},
    )
    password_headers = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password_headers)
    verification = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password_headers,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verification.cookies[SESSION_COOKIE]}"}


def test_authenticated_operations_contract_controls_integrations_jobs_notifications_and_audit() -> None:
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
        assert client.get("/api/v1/jobs").status_code == 401
        headers = _headers(client)

        catalog = client.get("/api/v1/integrations/providers", headers=headers)
        assert catalog.status_code == 200
        assert {item["provider"] for item in catalog.json()["items"]} >= {
            "MT5_TERMINAL_BRIDGE",
            "EMAIL",
            "TELEGRAM",
        }
        configured = client.post(
            "/api/v1/integrations/non-broker",
            headers={**headers, "Idempotency-Key": "email-integration-create-0001"},
            json={
                "provider": "EMAIL",
                "name": "Owner email",
                "configuration": {
                    "sender": "alerts@example.com",
                    "recipient": "owner@example.com",
                },
                "credentials": {"api_token": "never-return-this-token"},
                "capabilities": ["NOTIFICATION_SEND"],
                "official_source": True,
            },
        )
        assert configured.status_code == 201
        assert configured.json()["credential"] == "WRITE_ONLY"
        assert "never-return-this-token" not in configured.text
        rotated = client.post(
            f"/api/v1/integrations/{configured.json()['id']}/credentials/rotate",
            headers={
                **headers,
                "If-Match": configured.headers["etag"],
                "Idempotency-Key": "email-integration-rotate-0001",
            },
            json={"credentials": {"api_token": "new-never-return-token"}},
        )
        assert rotated.status_code == 200
        assert rotated.json()["state"] == "DEGRADED"
        assert "new-never-return-token" not in rotated.text

        with factory.begin() as database:
            job = BackgroundJob(
                job_type="MARKET_RESEARCH",
                state=JobState.RUNNING,
                context={},
                input_manifest={},
                progress={"stage": "SCREENING"},
                started_at=datetime(2026, 8, 14, tzinfo=UTC),
            )
            database.add(job)
            database.flush()
            job_id = job.id
        event_stream = client.get(f"/api/v1/jobs/{job_id}/events", headers=headers)
        assert event_stream.status_code == 200
        assert "event: job" in event_stream.text
        paused = client.post(
            f"/api/v1/jobs/{job_id}/actions",
            headers={**headers, "Idempotency-Key": "job-pause-request-0001"},
            json={"action": "PAUSE"},
        )
        assert paused.status_code == 202
        assert paused.json()["pause_requested"] is True

        preference = client.put(
            "/api/v1/notifications/preferences/EMAIL",
            headers=headers,
            json={"channel": "EMAIL", "minimum_severity": "WARNING", "enabled": True},
        )
        assert preference.status_code == 200
        tested = client.post("/api/v1/notifications/channels/EMAIL/test", headers=headers)
        assert tested.status_code == 202
        assert tested.json()["web_inbox_copy"] is True
        assert client.get("/api/v1/notifications/inbox", headers=headers).json()["items"]

        health = client.get("/api/v1/operations/health", headers=headers)
        assert health.status_code == 200
        assert health.json()["secrets_redacted"] is True
        audit = client.get(
            "/api/v1/operations/audit?action=integration.credential.rotate", headers=headers
        )
        assert audit.status_code == 200
        assert audit.json()["append_only"] is True
        assert audit.json()["items"][0]["previous_value"]["credential_version"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
