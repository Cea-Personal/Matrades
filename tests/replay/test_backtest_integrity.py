from datetime import UTC, datetime, timedelta

import pytest

from modules.backtesting.replay import chronological_replay


def test_replay_rejects_nonchronological_and_hides_future():
    now = datetime.now(UTC)
    rows = [
        {"observed_at": now, "value": 1, "future": 99},
        {"observed_at": now + timedelta(1), "value": 2, "future": 99},
    ]
    assert chronological_replay(rows, lambda x: "future" not in x) == [True, True]
    with pytest.raises(ValueError):
        chronological_replay(list(reversed(rows)), lambda x: True)
