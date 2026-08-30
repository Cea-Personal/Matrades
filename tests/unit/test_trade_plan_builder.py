from decimal import Decimal
from uuid import uuid4

from modules.accounts.models import AccountSnapshot
from modules.policy.models import EffectiveConstraint
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, RiskContext
from modules.risk.reservations import ReservationBook
from modules.trading.construction import build_trade_plan
from modules.trading.models import Direction, TradeConstruction, TradePlanState
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit


def _context() -> RiskContext:
    account = AccountSnapshot(
        account_id=uuid4(),
        starting_balance=Decimal("100000"),
        current_balance=Decimal("100000"),
        current_equity=Decimal("100000"),
        floating_pnl=Decimal("0"),
        realized_daily_pnl=Decimal("0"),
        source="test",
        source_version="1",
    )
    return RiskContext(
        account=account,
        constraints=[
            EffectiveConstraint(
                kind=kind,
                value=Decimal("2000"),
                source="test",
                source_version="1",
                reason="unit test",
            )
            for kind in (
                "MAX_TOTAL_DRAWDOWN",
                "MAX_DAILY_LOSS",
                "MAX_PORTFOLIO_RISK",
            )
        ],
    )


def _candidate() -> CandidateTrade:
    return CandidateTrade(
        instrument="EURUSD",
        direction=Direction.BUY,
        market_category="forex",
        requested_size=Decimal("1"),
        entry_price=Decimal("1.1"),
        stop_loss=Decimal("1.09"),
        risk_per_unit=Decimal("100"),
        size_increment=Decimal("0.01"),
    )


def test_build_trade_plan_binds_risk_size_and_evidence() -> None:
    context = _context()
    risk = RiskEngine().evaluate(context, _candidate())
    construction = TradeConstruction(
        instrument="EURUSD",
        direction=Direction.BUY,
        entry=Decimal("1.1"),
        stop_loss=Decimal("1.09"),
        targets=[Decimal("1.12")],
        invalidation="close below stop",
        approved_size=Decimal("1"),
        quantity_unit=QuantityUnit.LOTS,
        asset_class=AssetClass.FOREX,
        instrument_type=InstrumentType.CFD,
        venue_instrument_id=uuid4(),
        specification_version_id=uuid4(),
    )
    plan = build_trade_plan(
        owner_id=uuid4(),
        account_id=context.account.account_id,
        construction=construction,
        strategy_version_id=uuid4(),
        market_fingerprint_id=uuid4(),
        risk=risk,
        evidence_refs=("research-cycle-1",),
        expires_at="2026-08-26T00:00:00Z",
        reservations=ReservationBook(),
    )
    assert plan.state is TradePlanState.READY
    assert plan.construction.approved_size == risk.approved_size
    assert plan.evidence_refs == ("research-cycle-1",)
    assert plan.reservation_id is not None
