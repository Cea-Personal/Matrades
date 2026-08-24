from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, RiskContext, RiskDecision
from modules.risk.reservations import ReservationBook
from modules.trading.critic import CriticResult
from modules.trading.models import TradeProposal


class ProposalService:
    def __init__(self, reservations: ReservationBook | None = None) -> None:
        self.reservations = reservations or ReservationBook()
        self.engine = RiskEngine()
        self.proposals: dict[UUID, TradeProposal] = {}

    def create(
        self,
        *,
        owner_id: UUID,
        account_id: UUID,
        context: RiskContext,
        candidate: CandidateTrade,
        targets: list[Decimal],
        invalidation: str,
        critic: CriticResult,
    ) -> TradeProposal:
        if not critic.accepted:
            raise ValueError(critic.explanation)
        result = self.engine.evaluate(context, candidate)
        if result.decision == RiskDecision.HARD_BLOCK:
            raise ValueError("hard-blocked candidates cannot enter HIL-2")
        proposal = TradeProposal(
            owner_id=owner_id,
            account_id=account_id,
            instrument=candidate.instrument,
            direction=candidate.direction,
            entry=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            targets=targets,
            invalidation=invalidation,
            approved_size=result.approved_size,
            risk=result,
            critic_result=critic.explanation,
        )
        portfolio_limit = next(
            (item.value for item in context.constraints if item.kind.value == "MAX_PORTFOLIO_RISK"),
            result.snapshot.portfolio_risk_after_trade,
        )
        reservation = self.reservations.reserve(
            account_id,
            proposal.id,
            result.snapshot.candidate_trade_risk,
            max(Decimal("0"), portfolio_limit - result.snapshot.existing_open_risk),
        )
        proposal = proposal.model_copy(update={"reservation_id": reservation.id})
        self.proposals[proposal.id] = proposal
        return proposal
