from uuid import uuid4

from bridges.mt5.commands import BridgeCommand, BridgeCommandQueue, BridgeReceipt
from modules.journal.service import JournalProjector
from packages.contracts.events import EventEnvelope


def test_duplicate_command_event_and_journal_are_idempotent() -> None:
    account = uuid4()
    command = BridgeCommand(
        account_id=account,
        action="PLACE_ORDER",
        idempotency_key="event-idempotent-1",
        payload={"quantity": "1"},
        authorization_id=uuid4(),
        authorization_digest="d",
    )
    queue = BridgeCommandQueue()
    assert queue.enqueue(command).command_id == queue.enqueue(command).command_id
    receipt = BridgeReceipt(
        command_id=command.command_id,
        account_id=account,
        idempotency_key=command.idempotency_key,
        state="ACKNOWLEDGED",
        outcome_certainty="CONFIRMED",
    )
    assert queue.receipt(receipt) == queue.receipt(receipt)
    event = EventEnvelope(
        event_type="trade.updated",
        owner_id=uuid4(),
        aggregate_id=uuid4(),
        aggregate_version=1,
        payload={},
    )
    projector = JournalProjector()
    projector.project(event)
    projector.project(event)
    assert len(projector.reconstruct(event.aggregate_id)) == 1
