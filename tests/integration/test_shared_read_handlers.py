"""Compatibility read routes retain identical data and authorization boundaries."""

from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import automation, trade_plans
from modules.identity.authorization import Actor, Role
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


async def test_trade_plan_route_aliases_preserve_owner_isolation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, foreign = uuid4(), uuid4()
    actor = Actor(uuid4(), owner, Role.OWNER)
    async with factory() as session:
        store = ResourceStore(session)
        own_plan = await store.create("trade_plan", owner, {"instrument": "EUR/USD"})
        other_plan = await store.create("trade_plan", foreign, {"instrument": "GBP/USD"})
        await session.commit()

    async def database():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(automation.router)
    app.include_router(trade_plans.router)
    app.dependency_overrides[current_actor] = lambda: actor
    app.dependency_overrides[get_db] = database
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for prefix in ("/trade-plans", "/automation/trade-plans"):
                response = await client.get(prefix)
                assert response.status_code == 200
                assert [item["id"] for item in response.json()] == [str(own_plan.id)]
                detail = await client.get(f"{prefix}/{own_plan.id}")
                assert detail.status_code == 200
                assert detail.json() == response.json()[0]
                denied = await client.get(f"{prefix}/{other_plan.id}")
                assert denied.status_code == 404
                assert denied.json() == {"detail": "trade plan not found"}
            app.dependency_overrides.pop(current_actor)
            assert (await client.get("/trade-plans")).status_code == 401
            assert (await client.get("/automation/trade-plans")).status_code == 401
    finally:
        await engine.dispose()
