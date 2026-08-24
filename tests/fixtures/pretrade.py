from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from modules.accounts.models import AccountSnapshot
from modules.policy.models import ConstraintKind, EffectiveConstraint
from modules.risk.models import CandidateTrade, Direction, RiskContext


def context(**overrides: object) -> RiskContext:
    account_id = uuid4()
    snapshot = AccountSnapshot(
        account_id=account_id,
        starting_balance=Decimal("200000"),
        current_balance=Decimal("190000"),
        current_equity=Decimal("189000"),
        floating_pnl=Decimal("-1000"),
        realized_daily_pnl=Decimal("-1100"),
        observed_at=datetime.now(UTC),
        source="mt5",
        source_version="fixture-1",
    )
    limits = [
        EffectiveConstraint(
            kind=ConstraintKind.MAX_TOTAL_DRAWDOWN,
            value=Decimal("16000"),
            source="prop",
            source_version="1",
            reason="8% total",
        ),
        EffectiveConstraint(
            kind=ConstraintKind.MAX_DAILY_LOSS,
            value=Decimal("4000"),
            source="prop",
            source_version="1",
            reason="daily",
        ),
        EffectiveConstraint(
            kind=ConstraintKind.MAX_PORTFOLIO_RISK,
            value=Decimal("3000"),
            source="internal",
            source_version="1",
            reason="portfolio",
        ),
    ]
    values = {
        "account": snapshot,
        "constraints": limits,
        "positions": [],
        "static_max_concurrent_trades": 3,
    }
    values.update(overrides)
    return RiskContext(**values)


def candidate(size: str = "1") -> CandidateTrade:
    return CandidateTrade(
        instrument="EURUSD",
        direction=Direction.BUY,
        market_category="forex",
        requested_size=Decimal(size),
        entry_price=Decimal("1.085"),
        stop_loss=Decimal("1.08"),
        risk_per_unit=Decimal("500"),
        size_increment=Decimal("0.01"),
        currency_exposures={"USD": Decimal("1")},
    )
