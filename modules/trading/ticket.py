"""Auditable, non-guaranteed pre-trade monetary scenarios in account currency."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from modules.risk.financial_math import type_aware_loss_per_unit
from modules.risk.live_terms import LiveTradeTerms
from modules.risk.models import Direction, RiskDecision, RiskResult
from packages.shared.domain_types import InstrumentType


class TargetScenario(BaseModel):
    price: Decimal = Field(gt=0)
    profit_before_costs: Decimal = Field(ge=0)
    research_fraction: Decimal | None = None
    broker_hard_take_profit: bool = False


class TradeTicket(BaseModel):
    account_currency: str
    entry_basis: str = "LATEST_CLOSED_CANDLE_INDICATIVE"
    requested_risk_limit: Decimal = Field(gt=0)
    potential_loss_before_costs: Decimal = Field(ge=0)
    targets: list[TargetScenario]
    costs_excluded: tuple[str, ...] = ("spread", "slippage", "commission", "financing")
    partial_targets_executable: bool = False
    note: str = (
        "Each profit scenario assumes the full approved size exits at that target. "
        "These are indicative scenarios, not guaranteed fills or expected returns. "
        "The broker order uses the first target as its hard take-profit; "
        "later targets and research fractions are informational only."
    )


def build_trade_ticket(
    *,
    terms: LiveTradeTerms,
    instrument_type: InstrumentType,
    direction: Direction,
    entry: Decimal,
    stop: Decimal,
    targets: list[Decimal],
    fractions: list[Decimal | None],
    risk_limit: Decimal,
    risk: RiskResult,
) -> TradeTicket:
    if risk.decision is RiskDecision.HARD_BLOCK or risk.approved_size <= 0:
        raise ValueError("blocked trade cannot have an executable ticket")
    terms.validate_size(risk.approved_size)
    if (direction is Direction.BUY and stop >= entry) or (
        direction is Direction.SELL and stop <= entry
    ):
        raise ValueError("stop loss must be on the loss side of the entry")
    if not targets or len(targets) != len(fractions):
        raise ValueError("strategy targets and allocation references are incomplete")
    if any(
        (direction is Direction.BUY and price <= entry)
        or (direction is Direction.SELL and price >= entry)
        for price in targets
    ):
        raise ValueError("take-profit price must be on the profitable side of entry")
    if any(fraction is not None and (fraction <= 0 or fraction > 1) for fraction in fractions):
        raise ValueError("research target fractions must be within (0, 1]")
    return TradeTicket(
        account_currency=terms.account_currency,
        requested_risk_limit=risk_limit,
        potential_loss_before_costs=risk.approved_size
        * type_aware_loss_per_unit(
            instrument_type=instrument_type,
            entry=entry,
            stop=stop,
            contract_multiplier=terms.contract_multiplier,
            tick_size=terms.tick_size,
            tick_value=terms.tick_value,
        ),
        targets=[
            TargetScenario(
                price=price,
                profit_before_costs=risk.approved_size
                * type_aware_loss_per_unit(
                    instrument_type=instrument_type,
                    entry=entry,
                    stop=price,
                    contract_multiplier=terms.contract_multiplier,
                    tick_size=terms.tick_size,
                    tick_value=terms.tick_value,
                ),
                research_fraction=fractions[index],
                broker_hard_take_profit=index == 0,
            )
            for index, price in enumerate(targets)
        ],
    )
