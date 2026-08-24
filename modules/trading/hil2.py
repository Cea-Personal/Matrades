from modules.risk.reservations import ReservationBook, ReservationState
from modules.trading.models import ApprovalDecision, Hil2Action, ProposalState, TradeProposal


def decide(
    proposal: TradeProposal, decision: ApprovalDecision, reservations: ReservationBook
) -> TradeProposal:
    if proposal.state != ProposalState.AWAITING_HIL2 or decision.proposal_id != proposal.id:
        raise ValueError("proposal is not awaiting this decision")
    if decision.action == Hil2Action.TAKE:
        if proposal.reservation_id:
            reservations.transition(proposal.reservation_id, ReservationState.CONFIRMED)
        return proposal.model_copy(update={"state": ProposalState.AWAITING_MANUAL_ENTRY})
    if proposal.reservation_id:
        reservations.transition(proposal.reservation_id, ReservationState.RELEASED)
    state = ProposalState.WAITING if decision.action == Hil2Action.WAIT else ProposalState.REJECTED
    return proposal.model_copy(update={"state": state})
