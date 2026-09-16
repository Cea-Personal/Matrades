from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.routes.automation import equity_history
from modules.identity.authorization import Actor, Role
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.fixture
async def database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        yield session
    await engine.dispose()


async def test_equity_history_is_account_scoped_bounded_and_excludes_private_fields(database):
    owner, outsider = uuid4(), uuid4()
    store = ResourceStore(database)
    account = await store.create("account", owner, {"currency": "USD"})
    other_account = await store.create("account", owner, {"currency": "EUR"})
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for index in range(122):
        record = await store.create(
            "broker_snapshot",
            owner,
            {
                "account_id": str(account.id),
                "observed_at": (start + timedelta(minutes=index)).isoformat(),
                "equity": str(10000 + index),
                "balance": "10000",
                "signature": "private-signature",
                "positions": [{"private": True}],
            },
        )
        record.created_at = start + timedelta(minutes=index)
    for snapshot_owner, account_id, state in [
        (outsider, account.id, "ACTIVE"),
        (owner, other_account.id, "ACTIVE"),
        (owner, account.id, "DELETED"),
    ]:
        await store.create(
            "broker_snapshot",
            snapshot_owner,
            {"account_id": str(account_id), "equity": "999999"},
            state=state,
        )
    await database.flush()
    result = await equity_history(account.id, Actor(uuid4(), owner, Role.VIEWER), database)
    assert result["account_id"] == str(account.id)
    assert result["currency"] == "USD"
    assert len(result["points"]) == 120
    assert result["points"][0]["equity"] == "10002"
    assert result["points"][-1]["equity"] == "10121"
    assert all(
        set(point) == {"id", "observed_at", "equity", "balance"} for point in result["points"]
    )


async def test_equity_history_hides_foreign_missing_and_deleted_accounts(database):
    owner = uuid4()
    store = ResourceStore(database)
    account = await store.create("account", owner, {"currency": "USD"})
    actor = Actor(uuid4(), owner, Role.VIEWER)
    assert (await equity_history(account.id, actor, database))["points"] == []
    foreign = await store.create("account", uuid4(), {})
    deleted = await store.create("account", owner, {}, state="DELETED")
    for account_id in [foreign.id, deleted.id, uuid4()]:
        with pytest.raises(HTTPException) as error:
            await equity_history(account_id, actor, database)
        assert error.value.status_code == 404
