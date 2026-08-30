from uuid import uuid4

import pytest

from bridges.mt5.commands import BridgeCommand, BridgeCommandQueue, BridgeReceipt


def test_command_queue_is_idempotent_and_receipts_close_the_command():
    queue = BridgeCommandQueue()
    account_id = uuid4()
    command = BridgeCommand(
        account_id=account_id,
        action="PLACE_ORDER",
        idempotency_key="entry-1234",
        payload={"quantity": "1"},
    )
    assert queue.enqueue(command).command_id == queue.enqueue(command).command_id
    polled = queue.poll(account_id)
    assert len(polled) == 1
    receipt = queue.receipt(
        BridgeReceipt(
            command_id=command.command_id,
            account_id=account_id,
            idempotency_key="entry-1234",
            state="ACKNOWLEDGED",
            outcome_certainty="CONFIRMED",
        )
    )
    assert receipt.command_id == command.command_id
    assert queue.pending[command.command_id].state == "ACKNOWLEDGED"


def test_same_idempotency_key_cannot_change_economic_payload():
    queue = BridgeCommandQueue()
    account_id = uuid4()
    queue.enqueue(
        BridgeCommand(
            account_id=account_id,
            action="PLACE_ORDER",
            idempotency_key="entry-1234",
            payload={"quantity": "1"},
        )
    )
    with pytest.raises(ValueError):
        queue.enqueue(
            BridgeCommand(
                account_id=account_id,
                action="PLACE_ORDER",
                idempotency_key="entry-1234",
                payload={"quantity": "2"},
            )
        )
