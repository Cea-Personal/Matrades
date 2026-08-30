from uuid import uuid4

from modules.trading.models import CommandState, ExecutionAction, ExecutionCommand
from modules.trading.reconciliation import reconcile_command
from modules.trading.reconciliation_decisions import retry_allowed


def test_unknown_command_outcome_requires_reconciliation_before_retry() -> None:
    command = ExecutionCommand(
        account_id=uuid4(),
        action=ExecutionAction.PLACE_ORDER,
        idempotency_key="reconcile-command-1",
        state=CommandState.OUTCOME_UNKNOWN,
    )
    result = reconcile_command(command, [], [object()])
    assert result.certainty.value == "UNCERTAIN"
    assert retry_allowed(result) is False
