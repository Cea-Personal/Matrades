from __future__ import annotations

from collections.abc import Generator

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.shared.db import Base, load_model_metadata
from traderx_api.dependencies import get_database_session
from traderx_api.main import app
from traderx_api.routes.identity import SESSION_COOKIE


def _owner(client: TestClient) -> dict[str, str]:
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "catalogue-owner@example.com", "password": "sufficiently-long-password"},
    )
    password = {"Cookie": f"{SESSION_COOKIE}={bootstrap.cookies[SESSION_COOKIE]}"}
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=password)
    verified = client.post(
        "/api/v1/auth/mfa/enroll/verify",
        headers=password,
        json={"code": pyotp.parse_uri(enrollment.json()["provisioning_uri"]).now()},
    )
    return {"Cookie": f"{SESSION_COOKIE}={verified.cookies[SESSION_COOKIE]}"}


def test_reviewed_catalogue_and_non_broker_lifecycle_are_secret_safe() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override() -> Generator[Session]:
        with factory() as database:
            yield database

    app.dependency_overrides[get_database_session] = override
    try:
        client = TestClient(app)
        headers = _owner(client)
        catalogue = client.get("/api/v1/integrations/providers", headers=headers)
        assert catalogue.status_code == 200
        items = {item["provider"]: item for item in catalogue.json()["items"]}
        assert set(items) >= {
            "CME_GROUP",
            "CBOE_FX_SPOT",
            "COINBASE_EXCHANGE",
            "LITELLM_PROXY",
        }
        assert items["CME_GROUP"]["entitlement_required"] is True
        assert items["LITELLM_PROXY"]["configuration_fields"] == ["base_url"]
        assert items["LITELLM_PROXY"]["credential_fields"] == ["virtual_key"]
        assert items["LITELLM_PROXY"]["credentials_are_write_only"] is True
        assert "OPENAI_RESPONSES" not in items
        assert "ANTHROPIC_MESSAGES" not in items

        created = client.post(
            "/api/v1/integrations/non-broker",
            headers={**headers, "Idempotency-Key": "catalog-litellm-create-0001"},
            json={
                "provider": "LITELLM_PROXY",
                "name": "Research LiteLLM",
                "configuration": {"base_url": "http://litellm:4000/v1"},
                "credentials": {"virtual_key": "never-return-litellm-secret"},
                "capabilities": ["LLM_ANALYSIS"],
                "official_source": True,
                "licensing_accepted": True,
                "retention_accepted": True,
                "reason": "Connect reviewed advisory analysis",
            },
        )
        assert created.status_code == 201
        assert created.json()["credential"] == "WRITE_ONLY"
        assert created.json()["catalogue_revision"] == "2026-08-20.v1"
        assert "never-return-litellm-secret" not in created.text
        integration_id = created.json()["id"]

        created_replay = client.post(
            "/api/v1/integrations/non-broker",
            headers={**headers, "Idempotency-Key": "catalog-litellm-create-0001"},
            json={
                "provider": "LITELLM_PROXY",
                "name": "Research LiteLLM",
                "configuration": {"base_url": "http://litellm:4000/v1"},
                "credentials": {"virtual_key": "never-return-litellm-secret"},
                "capabilities": ["LLM_ANALYSIS"],
                "official_source": True,
                "licensing_accepted": True,
                "retention_accepted": True,
                "reason": "Connect reviewed advisory analysis",
            },
        )
        assert created_replay.status_code == 201
        assert created_replay.json() == created.json()
        conflicting_create = client.post(
            "/api/v1/integrations/non-broker",
            headers={**headers, "Idempotency-Key": "catalog-litellm-create-0001"},
            json={
                "provider": "LITELLM_PROXY",
                "name": "A different integration",
                "configuration": {"base_url": "http://litellm:4000/v1"},
                "credentials": {"virtual_key": "never-return-litellm-secret"},
                "capabilities": ["LLM_ANALYSIS"],
                "official_source": True,
                "licensing_accepted": True,
                "retention_accepted": True,
                "reason": "Connect reviewed advisory analysis",
            },
        )
        assert conflicting_create.status_code == 409

        rotated = client.post(
            f"/api/v1/integrations/{integration_id}/credentials/rotate",
            headers={
                **headers,
                "If-Match": created.headers["etag"],
                "Idempotency-Key": "catalog-litellm-rotate-0001",
            },
            json={"credentials": {"virtual_key": "second-never-return-litellm-secret"}},
        )
        assert rotated.status_code == 200
        assert rotated.json()["credential_status"] == "CONFIGURED"
        assert "second-never-return-litellm-secret" not in rotated.text
        rotated_replay = client.post(
            f"/api/v1/integrations/{integration_id}/credentials/rotate",
            headers={
                **headers,
                "If-Match": created.headers["etag"],
                "Idempotency-Key": "catalog-litellm-rotate-0001",
            },
            json={"credentials": {"virtual_key": "second-never-return-litellm-secret"}},
        )
        assert rotated_replay.status_code == 200
        assert rotated_replay.json() == rotated.json()

        qualification = client.post(
            f"/api/v1/integrations/{integration_id}/test",
            headers={**headers, "Idempotency-Key": "catalog-litellm-test-0001"},
        )
        assert qualification.status_code == 202
        assert qualification.json()["state"] == "QUEUED"
        assert qualification.json()["credential"] == "REDACTED"
        qualification_replay = client.post(
            f"/api/v1/integrations/{integration_id}/test",
            headers={**headers, "Idempotency-Key": "catalog-litellm-test-0001"},
        )
        assert qualification_replay.status_code == 202
        assert qualification_replay.json() == qualification.json()

        listed = client.get("/api/v1/integrations/non-broker", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["provider"] == "LITELLM_PROXY"
        assert "never-return-litellm-secret" not in listed.text

        disabled = client.put(
            f"/api/v1/integrations/{integration_id}/non-broker/state",
            headers={
                **headers,
                "If-Match": rotated.headers["etag"],
                "Idempotency-Key": "catalog-litellm-disable-0001",
            },
            json={"action": "DISABLE", "reason": "Pause advisory analysis provider"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["state"] == "DISABLED"
        disabled_replay = client.put(
            f"/api/v1/integrations/{integration_id}/non-broker/state",
            headers={
                **headers,
                "If-Match": rotated.headers["etag"],
                "Idempotency-Key": "catalog-litellm-disable-0001",
            },
            json={"action": "DISABLE", "reason": "Pause advisory analysis provider"},
        )
        assert disabled_replay.status_code == 200
        assert disabled_replay.json() == disabled.json()

        removed = client.delete(
            f"/api/v1/integrations/{integration_id}",
            headers={
                **headers,
                "If-Match": disabled.headers["etag"],
                "Idempotency-Key": "catalog-litellm-remove-0001",
            },
        )
        assert removed.status_code == 200
        assert removed.json()["status"] == "REMOVED"
        removed_replay = client.delete(
            f"/api/v1/integrations/{integration_id}",
            headers={
                **headers,
                "If-Match": disabled.headers["etag"],
                "Idempotency-Key": "catalog-litellm-remove-0001",
            },
        )
        assert removed_replay.status_code == 200
        assert removed_replay.json() == removed.json()

        cme = client.post(
            "/api/v1/integrations/non-broker",
            headers={**headers, "Idempotency-Key": "catalog-cme-create-0001"},
            json={
                "provider": "CME_GROUP",
                "name": "CME commodities",
                "configuration": {"project_id": "licensed-project"},
                "credentials": {"api_token": "never-return-cme-secret"},
                "capabilities": ["MARKET_DATA_READ"],
                "official_source": True,
                "licensing_accepted": True,
                "retention_accepted": False,
                "reason": "Connect entitled commodity evidence",
            },
        )
        assert cme.status_code == 201
        declared = client.put(
            f"/api/v1/integrations/{cme.json()['id']}/entitlement",
            headers={
                **headers,
                "If-Match": cme.headers["etag"],
                "Idempotency-Key": "catalog-cme-entitlement-0001",
            },
            json={
                "confirmation": "CONFIRM_ENTITLEMENT",
                "evidence_reference": "agreement-2026-08",
                "reason": "Record paid CME entitlement evidence",
            },
        )
        assert declared.status_code == 200
        assert declared.json()["entitlement_status"] == "DECLARED"
        assert "agreement-2026-08" not in declared.text
        declared_replay = client.put(
            f"/api/v1/integrations/{cme.json()['id']}/entitlement",
            headers={
                **headers,
                "If-Match": cme.headers["etag"],
                "Idempotency-Key": "catalog-cme-entitlement-0001",
            },
            json={
                "confirmation": "CONFIRM_ENTITLEMENT",
                "evidence_reference": "agreement-2026-08",
                "reason": "Record paid CME entitlement evidence",
            },
        )
        assert declared_replay.status_code == 200
        assert declared_replay.json() == declared.json()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
