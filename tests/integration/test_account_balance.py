from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.routes.configuration import (
    AccountInput,
    create_account,
    list_accounts,
    update_account,
)
from modules.identity.authorization import Actor, Role
from modules.risk.authority import authoritative_risk_context
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, Direction, RiskDecision
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


def _candidate() -> CandidateTrade:
    return CandidateTrade(
        instrument="EURUSD",
        direction=Direction.BUY,
        market_category="forex",
        requested_size=Decimal("1"),
        entry_price=Decimal("1.1"),
        stop_loss=Decimal("1.09"),
        risk_per_unit=Decimal("100"),
    )


async def test_account_persists_opening_current_balance_without_making_it_risk_authority(database):
    owner = uuid4()
    actor = Actor(uuid4(), owner, Role.OWNER)
    created = await create_account(
        AccountInput(
            name="Primary", currency="USD", starting_balance=Decimal("10000"),
            current_balance=Decimal("8500"),
        ),
        actor,
        database,
    )
    assert created["starting_balance"] == "10000"
    assert created["current_balance"] == "8500"
    assert (await list_accounts(actor, database))[0]["current_balance"] == "8500"

    account_id = UUID(created["id"])
    with pytest.raises(HTTPException, match="fresh broker equity snapshot"):
        await authoritative_risk_context(database, owner, account_id, _candidate())

    await ResourceStore(database).create(
        "broker_snapshot", owner,
        {
            "account_id": str(account_id),
            "sequence": 1,
            "observed_at": datetime.now(UTC).isoformat(),
            "balance": "9000",
            "equity": "8800",
            "realized_daily_pnl": "-100",
            "account_currency": "USD",
            "positions": [],
            "signature": "test-snapshot",
        },
    )
    await ResourceStore(database).create(
        "guardrail", owner,
        {
            "name": "Account limits",
            "account_id": str(account_id),
            "rules": [
                {"kind": "MAX_TOTAL_DRAWDOWN", "value": "1300", "enforcement": "HARD"},
                {"kind": "MAX_DAILY_LOSS", "value": "1000", "enforcement": "HARD"},
                {"kind": "MAX_PORTFOLIO_RISK", "value": "1000", "enforcement": "HARD"},
                {"kind": "MAX_RISK_PER_TRADE", "value": "1000", "enforcement": "HARD"},
            ],
        },
    )
    context = await authoritative_risk_context(database, owner, account_id, _candidate())
    assert context.account.starting_balance == Decimal("10000")
    assert context.account.current_balance == Decimal("9000")
    assert context.account.current_equity == Decimal("8800")
    result = RiskEngine().evaluate(context, _candidate())
    assert result.decision is RiskDecision.PASS
    assert result.snapshot.remaining_drawdown == Decimal("100")


async def test_legacy_account_defaults_and_patch_preserves_opening_value(database):
    actor = Actor(uuid4(), uuid4(), Role.OWNER)
    created = await create_account(
        AccountInput(name="Legacy", starting_balance=Decimal("10000")), actor, database,
    )
    assert created["current_balance"] == "10000"
    updated = await update_account(
        UUID(created["id"]),
        AccountInput(name="Renamed", starting_balance=Decimal("10000")),
        actor, database,
    )
    assert updated["current_balance"] == "10000"
    with pytest.raises(ValidationError):
        AccountInput(
            name="Invalid", starting_balance=Decimal("10000"), current_balance=Decimal("0")
        )
