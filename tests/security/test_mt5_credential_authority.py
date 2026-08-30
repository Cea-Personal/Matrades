import base64
import hashlib
import hmac
import time
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import get_db
from apps.api.app.main import create_app
from modules.connections.models import ConnectionProvider
from modules.connections.mt5_authority import verify_ui_managed_mt5_signature
from modules.credentials.vault import EnvelopeCipher
from packages.shared.config import get_settings
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


async def test_ui_managed_linked_credential_is_mt5_signature_authority(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'authority.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid4()
    secret = "ui-managed-bridge-secret"  # noqa: S105 - isolated test credential
    cipher = EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())

    async with factory() as session:
        store = ResourceStore(session)
        envelope = cipher.encrypt(owner_id, secret)
        credential = await store.create(
            "credential",
            owner_id,
            {
                "name": "MT5",
                "provider": ConnectionProvider.MT5_BRIDGE.value,
                "purpose": "broker",
                "envelope": envelope.as_dict(),
            },
        )
        await store.create(
            "connection",
            owner_id,
            {
                "name": "Local MT5",
                "provider": ConnectionProvider.MT5_BRIDGE.value,
                "credential_id": str(credential.id),
                "active": True,
            },
        )
        await session.commit()

        body = b'{"account_id":"test"}'
        timestamp = str(int(time.time()))
        nonce = uuid4().hex
        signed = timestamp.encode() + b"." + nonce.encode() + b"." + body
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        matched = await verify_ui_managed_mt5_signature(
            session,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
        )
        assert matched == credential.id

        invalid = await verify_ui_managed_mt5_signature(
            session,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
            signature="0" * 64,
        )
        assert invalid is None

    async def test_db():
        async with factory() as session:
            yield session

    app = create_app(engine)
    app.dependency_overrides[get_db] = test_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        authenticated = await client.post(
            "/api/v1/internal/mt5/authenticate",
            headers={"X-Matrades-Service-Token": "development-mt5-authority-token"},
            json={
                "body_base64": base64.b64encode(body).decode(),
                "timestamp": timestamp,
                "nonce": nonce,
                "signature": signature,
            },
        )
        assert authenticated.status_code == 200
        assert authenticated.json()["credential_id"] == str(credential.id)

        unauthorized_service = await client.post(
            "/api/v1/internal/mt5/authenticate",
            headers={"X-Matrades-Service-Token": "wrong"},
            json={
                "body_base64": "",
                "timestamp": timestamp,
                "nonce": nonce,
                "signature": signature,
            },
        )
        assert unauthorized_service.status_code == 401

    await engine.dispose()
