from uuid import uuid4

from bridges.mt5.commands import BridgeCommand, BridgeReceipt


def bridge_command() -> BridgeCommand:
    return BridgeCommand(
        account_id=uuid4(),
        action="PLACE_ORDER",
        idempotency_key="fixture-command-1",
        authorization_id=uuid4(),
        authorization_digest="fixture-digest",
        payload={"instrument": "EURUSD", "direction": "BUY", "quantity": "1"},
    )


def bridge_receipt(command: BridgeCommand) -> BridgeReceipt:
    return BridgeReceipt(
        command_id=command.command_id,
        account_id=command.account_id,
        idempotency_key=command.idempotency_key,
        state="ACKNOWLEDGED",
        outcome_certainty="CONFIRMED",
        broker_order_id="fixture-order-1",
    )
