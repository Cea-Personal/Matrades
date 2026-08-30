from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx

from modules.connections.models import ConnectionProfile, ConnectionProvider
from modules.connections.testing import probe_connection, twelve_data_check_due


def test_visible_connection_catalog_covers_data_sources_and_mt5() -> None:
    assert set(ConnectionProvider) == {
        ConnectionProvider.TWELVE_DATA,
        ConnectionProvider.COINBASE,
        ConnectionProvider.COINGECKO,
        ConnectionProvider.FRED,
        ConnectionProvider.CFTC,
        ConnectionProvider.FUTURES_REFERENCE,
        ConnectionProvider.CALENDAR,
        ConnectionProvider.NEWS,
        ConnectionProvider.FOREX_FACTORY,
        ConnectionProvider.SERPAPI,
        ConnectionProvider.OPENAI,
        ConnectionProvider.MT5_BRIDGE,
    }


async def test_mt5_probe_uses_real_health_response_and_reports_capabilities() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Signature"]
        assert request.headers["X-Nonce"]
        return httpx.Response(
            200,
            json={
                "status": "healthy",
                "fresh": True,
                "bridge_version": "1.2.0",
                "capabilities": ["accounts.read", "positions.read", "history.read"],
                "writes": True,
            },
        )

    profile = ConnectionProfile(
        name="Local MT5",
        provider=ConnectionProvider.MT5_BRIDGE,
        credential_id=uuid4(),
        configuration={"bridge_url": "http://127.0.0.1:8765", "account_reference": "demo"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "bridge-secret", client=client)

    assert result.status == "HEALTHY"
    assert result.writes is True
    assert "positions.read" in result.capabilities


async def test_mt5_probe_explains_reachable_bridge_without_fresh_ea_snapshot() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "waiting_for_ea",
                "fresh": False,
                "bridge_version": "1.2.0",
                "capabilities": ["accounts.read", "positions.read", "history.read"],
                "writes": False,
            },
        )

    profile = ConnectionProfile(
        name="Local MT5",
        provider=ConnectionProvider.MT5_BRIDGE,
        credential_id=uuid4(),
        configuration={"bridge_url": "http://127.0.0.1:8765", "account_reference": "demo"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "bridge-secret", client=client)

    assert result.status == "STALE"
    assert result.safe_message is not None
    assert "Enable Algorithmic Trading" in result.safe_message
    assert "WebRequest" in result.safe_message


async def test_mt5_stale_probe_warns_when_bridge_advertises_write_capability() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "waiting_for_ea",
                "fresh": False,
                "capabilities": ["accounts.read", "positions.read"],
                "writes": True,
            },
        )

    profile = ConnectionProfile(
        name="Execution MT5",
        provider=ConnectionProvider.MT5_BRIDGE,
        credential_id=uuid4(),
        configuration={"bridge_url": "http://127.0.0.1:8765", "account_reference": "demo"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "bridge-secret", client=client)

    assert result.safe_message is not None
    assert "broker-write capability" in result.safe_message
    assert "every attached EA" in result.safe_message


async def test_twelve_data_probe_validates_key_without_requesting_a_symbol() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api_usage"
        assert "symbol" not in request.url.params
        assert "apikey" not in request.url.params
        assert request.headers["Authorization"] == "apikey right-key"
        return httpx.Response(
            200,
            json={"status": "ok", "plan": "basic", "credits_left": 100},
        )

    profile = ConnectionProfile(
        name="Twelve Data",
        provider=ConnectionProvider.TWELVE_DATA,
        credential_id=uuid4(),
        configuration={"forex_universe": "EUR/USD,GBP/USD"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "right-key", client=client)

    assert result.status == "HEALTHY"
    assert "forex.read" in result.capabilities
    assert "market.discovery" in result.capabilities


async def test_openai_probe_advertises_embedding_capability() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer project-key"
        return httpx.Response(200, json={"data": [{"id": "text-embedding-3-small"}]})

    profile = ConnectionProfile(
        name="OpenAI knowledge embeddings",
        provider=ConnectionProvider.OPENAI,
        credential_id=uuid4(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_connection(profile, "project-key", client=client)

    assert result.status == "HEALTHY"
    assert "embeddings.create" in result.capabilities


def test_twelve_data_health_is_throttled_for_one_hour() -> None:
    now = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)

    assert not twelve_data_check_due("2026-08-25T09:30:00+00:00", now=now)
    assert twelve_data_check_due("2026-08-25T08:59:59+00:00", now=now)
    assert twelve_data_check_due(None, now=now)
