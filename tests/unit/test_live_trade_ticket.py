from decimal import Decimal
from uuid import uuid4

import pytest

from modules.policy.models import ConstraintKind, EffectiveConstraint
from modules.risk.engine import RiskEngine
from modules.risk.live_terms import LiveTradeTerms
from modules.risk.models import CandidateTrade, Direction, RiskDecision
from modules.trading.ticket import build_trade_ticket
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit
from tests.fixtures.pretrade import context


def _terms() -> LiveTradeTerms:
    return LiveTradeTerms(
        account_currency="USD",
        price_currency="USD",
        quantity_unit=QuantityUnit.LOTS,
        contract_multiplier=Decimal("100"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1"),
        quantity_minimum=Decimal("0.01"),
        quantity_maximum=Decimal("50"),
        quantity_step=Decimal("0.01"),
        specification_version_id=uuid4(),
    )


def _risk(terms: LiveTradeTerms, *, budget: str = "155", cost: str = "0"):
    venue_id = uuid4()
    candidate = CandidateTrade(
        instrument="XAUUSD",
        direction=Direction.BUY,
        market_category="metals",
        requested_size=terms.quantity_maximum,
        entry_price=Decimal("2500"),
        stop_loss=Decimal("2490"),
        risk_per_unit=Decimal("1000"),
        size_increment=terms.quantity_step,
        asset_class=AssetClass.METALS,
        instrument_type=InstrumentType.CFD,
        venue_instrument_id=venue_id,
        specification_version_id=terms.specification_version_id,
        quantity_unit=terms.quantity_unit,
        contract_multiplier=terms.contract_multiplier,
        tick_size=terms.tick_size,
        tick_value=terms.tick_value,
        financing_cost=Decimal(cost),
    )
    base = context()
    return RiskEngine().evaluate(
        base.model_copy(
            update={
                "constraints": [
                    *base.constraints,
                    EffectiveConstraint(
                        kind=ConstraintKind.MAX_RISK_PER_TRADE,
                        value=Decimal(budget),
                        source="internal:live-ticket",
                        source_version="1",
                        reason="cash risk cap",
                    ),
                ],
                "instrument_specifications": {
                    str(terms.specification_version_id): {
                        "freshness": "VALID",
                        "source_cut_id": "mt5:1",
                    }
                },
                "current_source_cut_id": "mt5:1",
            }
        ),
        candidate,
    )


def test_broker_native_lot_rounding_and_target_scenarios() -> None:
    terms = _terms()
    risk = _risk(terms)
    assert risk.decision is RiskDecision.REDUCE_SIZE
    assert risk.approved_size == Decimal("0.15")
    assert risk.snapshot.candidate_trade_risk == Decimal("150")
    ticket = build_trade_ticket(
        terms=terms,
        instrument_type=InstrumentType.CFD,
        direction=Direction.BUY,
        entry=Decimal("2500"),
        stop=Decimal("2490"),
        targets=[Decimal("2515"), Decimal("2530")],
        fractions=[Decimal("0.5"), Decimal("0.5")],
        risk_limit=Decimal("155"),
        risk=risk,
    )
    assert ticket.potential_loss_before_costs == Decimal("150")
    assert [item.profit_before_costs for item in ticket.targets] == [
        Decimal("225.00"),
        Decimal("450.00"),
    ]
    assert ticket.targets[0].broker_hard_take_profit
    assert not ticket.targets[1].broker_hard_take_profit
    assert not ticket.partial_targets_executable


def test_fixed_cost_consumes_capacity_before_lot_rounding() -> None:
    risk = _risk(_terms(), budget="155", cost="10")
    assert risk.approved_size == Decimal("0.14")
    assert risk.snapshot.candidate_trade_risk == Decimal("150")


def test_native_minimum_and_stop_side_fail_closed() -> None:
    terms = _terms()
    risk = _risk(terms, budget="5")
    assert risk.approved_size == Decimal("0")
    assert risk.decision is RiskDecision.HARD_BLOCK
    with pytest.raises(ValueError, match="blocked trade"):
        build_trade_ticket(
            terms=terms,
            instrument_type=InstrumentType.CFD,
            direction=Direction.BUY,
            entry=Decimal("2500"),
            stop=Decimal("2490"),
            targets=[Decimal("2515")],
            fractions=[None],
            risk_limit=Decimal("5"),
            risk=risk,
        )
    risk = _risk(terms)
    with pytest.raises(ValueError, match="stop loss"):
        build_trade_ticket(
            terms=terms,
            instrument_type=InstrumentType.CFD,
            direction=Direction.BUY,
            entry=Decimal("2500"),
            stop=Decimal("2510"),
            targets=[Decimal("2520")],
            fractions=[None],
            risk_limit=Decimal("155"),
            risk=risk,
        )
