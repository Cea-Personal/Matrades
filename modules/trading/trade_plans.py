from __future__ import annotations

from uuid import UUID

from modules.risk.models import RiskDecision, RiskResult
from modules.risk.reservations import ReservationBook
from modules.trading.models import TradeConstruction, TradePlan, TradePlanState


def build_trade_plan(
    *,
    owner_id: UUID,
    account_id: UUID,
    construction: TradeConstruction,
    strategy_version_id: UUID,
    market_fingerprint_id: UUID,
    risk: RiskResult,
    evidence_refs: tuple[str, ...],
    expires_at,
    reservations: ReservationBook | None = None,
) -> TradePlan:
    """Construct a typed immutable-at-boundary plan from deterministic risk output."""
    if risk.decision is RiskDecision.HARD_BLOCK:
        state = TradePlanState.BLOCKED
    else:
        state = TradePlanState.READY
    if construction.approved_size != risk.approved_size:
        construction = construction.model_copy(update={"approved_size": risk.approved_size})
    plan = TradePlan(
        owner_id=owner_id,
        account_id=account_id,
        state=state,
        construction=construction,
        strategy_version_id=strategy_version_id,
        market_fingerprint_id=market_fingerprint_id,
        risk=risk,
        evidence_refs=evidence_refs,
        expires_at=expires_at,
    )
    if reservations is None or risk.decision is RiskDecision.HARD_BLOCK:
        return plan
    reservation = reservations.reserve(
        account_id=account_id,
        proposal_id=plan.id,
        amount=risk.snapshot.candidate_trade_risk,
        available=risk.snapshot.remaining_portfolio_risk_capacity,
    )
    return plan.model_copy(update={"reservation_id": reservation.id})


_PLAN_TRANSITIONS: dict[TradePlanState, set[TradePlanState]] = {
    TradePlanState.CONSTRUCTED: {TradePlanState.VALIDATING, TradePlanState.BLOCKED},
    TradePlanState.VALIDATING: {TradePlanState.READY, TradePlanState.BLOCKED},
    TradePlanState.READY: {
        TradePlanState.AUTHORIZED,
        TradePlanState.EXPIRED,
        TradePlanState.BLOCKED,
    },
    TradePlanState.AUTHORIZED: {
        TradePlanState.EXECUTION_PENDING,
        TradePlanState.REVALIDATION_REQUIRED,
    },
    TradePlanState.EXECUTION_PENDING: {
        TradePlanState.EXECUTING,
        TradePlanState.REVALIDATION_REQUIRED,
    },
    TradePlanState.EXECUTING: {TradePlanState.ACTIVE, TradePlanState.REVALIDATION_REQUIRED},
    TradePlanState.ACTIVE: {TradePlanState.EXPIRED, TradePlanState.CANCELLED},
}


def transition_trade_plan(plan: TradePlan, target: TradePlanState) -> TradePlan:
    if target is plan.state:
        return plan
    if target not in _PLAN_TRANSITIONS.get(plan.state, set()):
        raise ValueError(f"cannot transition Trade Plan {plan.state} to {target}")
    return plan.model_copy(update={"state": target, "version": plan.version + 1})
