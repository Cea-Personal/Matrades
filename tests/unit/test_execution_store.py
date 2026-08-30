from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from modules.trading.execution_store import lease_expired


def test_lease_expiry_is_fail_closed() -> None:
    record = SimpleNamespace(data={})
    assert lease_expired(record)
    future = datetime.now(UTC) + timedelta(minutes=1)
    record.data = {"lease": {"expires_at": future.isoformat()}}
    assert lease_expired(record, now=datetime.now(UTC)) is False
