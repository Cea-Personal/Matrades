from __future__ import annotations

from apps.api.app.routes import operations


class FakeRedis:
    def __init__(self, heartbeat: bytes | None) -> None:
        self.heartbeat = heartbeat
        self.closed = False

    async def get(self, _: str) -> bytes | None:
        return self.heartbeat

    async def aclose(self) -> None:
        self.closed = True


async def test_codex_health_requires_a_fresh_worker_heartbeat(monkeypatch) -> None:
    redis = FakeRedis(b"healthy")
    monkeypatch.setattr(operations.Redis, "from_url", lambda _: redis)

    result = await operations.codex_app_server_health()

    assert result["state"] == "HEALTHY"
    assert result["fresh"] is True
    assert redis.closed is True


async def test_codex_health_is_offline_without_worker_heartbeat(monkeypatch) -> None:
    redis = FakeRedis(None)
    monkeypatch.setattr(operations.Redis, "from_url", lambda _: redis)

    result = await operations.codex_app_server_health()

    assert result["state"] == "OFFLINE"
    assert result["fresh"] is False
