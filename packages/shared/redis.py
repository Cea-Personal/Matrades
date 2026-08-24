from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis


class EphemeralState:
    """Cache/lock wrapper that must never be used as a system of record."""

    authoritative = False

    def __init__(self, client: Redis) -> None:
        self.client = client

    async def get(self, key: str) -> bytes | None:
        return await self.client.get(key)

    async def set_cache(self, key: str, value: bytes, ttl_seconds: int) -> None:
        await self.client.set(key, value, ex=ttl_seconds)

    @asynccontextmanager
    async def lock(self, key: str, lease_seconds: int = 15) -> AsyncIterator[None]:
        lock = self.client.lock(f"lock:{key}", timeout=lease_seconds)
        if not await lock.acquire(blocking=False):
            raise RuntimeError("resource is busy")
        try:
            yield
        finally:
            await lock.release()
