from uuid import uuid4

import pytest

from modules.trading.execution import CommandTransitionError, transition
from modules.trading.models import CommandState, ExecutionAction, ExecutionCommand


def test_command_state_machine_rejects_terminal_reuse() -> None:
    command = ExecutionCommand(
        account_id=uuid4(),
        action=ExecutionAction.PLACE_ORDER,
        idempotency_key="terminal-command-1",
        state=CommandState.ACKNOWLEDGED,
    )
    with pytest.raises(CommandTransitionError):
        transition(command, CommandState.DISPATCHING)
