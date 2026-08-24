from decimal import Decimal
from uuid import uuid4

from modules.risk.engine import RiskEngine
from modules.risk.reservations import ReservationBook, ReservationState
from modules.trading.hil2 import decide
from modules.trading.models import ApprovalDecision, Hil2Action, ProposalState, TradeProposal
from tests.fixtures.pretrade import candidate, context


def proposal(book: ReservationBook) -> TradeProposal:
    item = TradeProposal(
        owner_id=uuid4(),
        account_id=uuid4(),
        instrument="EURUSD",
        direction="BUY",
        entry=Decimal("1.1"),
        stop_loss=Decimal("1"),
        targets=[Decimal("1.2")],
        invalidation="structure",
        approved_size=Decimal("1"),
        risk=RiskEngine().evaluate(context(), candidate()),
        critic_result="ok",
    )
    reservation = book.reserve(item.account_id, item.id, Decimal("500"), Decimal("1000"))
    return item.model_copy(update={"reservation_id": reservation.id})


def test_take_records_intent_without_execution() -> None:
    book = ReservationBook()
    item = proposal(book)
    result = decide(
        item, ApprovalDecision(proposal_id=item.id, actor_id=uuid4(), action=Hil2Action.TAKE), book
    )
    assert result.state == ProposalState.AWAITING_MANUAL_ENTRY
    assert book._items[item.reservation_id].state == ReservationState.CONFIRMED
