from uuid import uuid4

import pytest

from modules.credentials.redaction import redact
from modules.trading.kill_switches import update_kill_switch
from modules.trading.models import KillSwitchState


def test_configuration_secrets_are_redacted_and_kill_switch_requires_step_up() -> None:
    assert redact({"api_key": "secret", "nested": {"token": "value"}})["api_key"] == "[REDACTED]"
    with pytest.raises(PermissionError):
        update_kill_switch(
            KillSwitchState(scope="ACCOUNT", account_id=uuid4()), step_up_verified=False
        )
