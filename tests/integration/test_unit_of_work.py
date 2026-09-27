"""One transaction boundary commits success and rolls back errors or cancellation."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.shared import database
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.mark.parametrize("failure", [RuntimeError("aborted"), asyncio.CancelledError()])
async def test_transaction_commits_success_and_rolls_back_failure(monkeypatch, failure) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "session_factory", factory)
    owner = uuid4()
    try:
        async with database.unit_of_work() as session:
            committed = await ResourceStore(session).create("account", owner, {"name": "Kept"})
        with pytest.raises(type(failure)) as caught:
            async with database.unit_of_work() as session:
                await ResourceStore(session).create("account", owner, {"name": "Rolled back"})
                raise failure
        assert caught.value is failure
        async with factory() as session:
            records = await ResourceStore(session).list("account", owner)
            assert [item.id for item in records] == [committed.id]
            assert records[0].data["name"] == "Kept"
    finally:
        await engine.dispose()
