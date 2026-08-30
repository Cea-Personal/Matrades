from uuid import uuid4

from bridges.mt5.commands import BridgeCommand, BridgeCommandQueue, BridgeReceipt


def test_bridge_queue_survives_restart_and_releases_lease_after_receipt(tmp_path) -> None:
    path = tmp_path / "commands.json"
    account_id = uuid4()
    command = BridgeCommand(
        account_id=account_id,
        action="PLACE_ORDER",
        idempotency_key="restart-command-1",
        authorization_id=uuid4(),
        authorization_digest="digest",
        payload={"instrument": "EURUSD", "quantity": "1"},
    )
    BridgeCommandQueue(str(path)).enqueue(command)
    restarted = BridgeCommandQueue(str(path))
    assert restarted.poll(account_id)[0].command_id == command.command_id
    restarted.receipt(
        BridgeReceipt(
            command_id=command.command_id,
            account_id=account_id,
            idempotency_key=command.idempotency_key,
            state="ACKNOWLEDGED",
            outcome_certainty="CONFIRMED",
        )
    )
    assert BridgeCommandQueue(str(path)).pending[command.command_id].state == "ACKNOWLEDGED"
