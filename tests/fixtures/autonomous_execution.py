"""Deterministic fixtures shared by autonomous execution tests."""

from decimal import Decimal
from uuid import uuid4

from modules.accounts.models import AccountSnapshot
from modules.risk.models import CandidateTrade, RiskContext
from modules.trading.models import Direction
from packages.shared.domain_types import utc_now


def account_snapshot() -> AccountSnapshot:
    return AccountSnapshot(
        account_id=uuid4(),
        starting_balance=Decimal("100000"),
        current_balance=Decimal("100000"),
        current_equity=Decimal("100000"),
        floating_pnl=Decimal("0"),
        realized_daily_pnl=Decimal("0"),
        source="fixture-broker",
        source_version="fixture-v1",
        observed_at=utc_now(),
    )


def candidate_trade() -> CandidateTrade:
    return CandidateTrade(
        instrument="EURUSD",
        direction=Direction.BUY,
        market_category="FOREX",
        requested_size=Decimal("1"),
        entry_price=Decimal("1.1"),
        stop_loss=Decimal("1.09"),
        risk_per_unit=Decimal("100"),
    )


def risk_context() -> RiskContext:
    from tests.fixtures.pretrade import context

    return context()
