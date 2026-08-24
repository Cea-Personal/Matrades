from uuid import UUID

from modules.trading.models import TradeProposal
from packages.contracts.events import EventEnvelope


def proposal_event(
    proposal: TradeProposal, event_type: str, actor_id: UUID | None = None
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        owner_id=proposal.owner_id,
        actor_id=actor_id,
        aggregate_id=proposal.id,
        aggregate_version=1,
        payload={
            "state": proposal.state,
            "risk_decision": proposal.risk.decision,
            "approved_size": str(proposal.approved_size),
            "authoritative": True,
        },
    )
