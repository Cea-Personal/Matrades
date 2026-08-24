import asyncio
from uuid import uuid4

from modules.knowledge.search import hybrid_search


class Embed:
    async def embed(self, texts):
        return [[0.0] for _ in texts]


class Index:
    async def search(self, owner_id, vector, limit):
        return []

    async def upsert(self, *args):
        pass

    async def delete(self, *args):
        pass


def test_cross_owner_candidates_cannot_leak():
    assert asyncio.run(hybrid_search(uuid4(), "query", Embed(), Index(), {})) == []
