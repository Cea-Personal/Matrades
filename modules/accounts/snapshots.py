from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from modules.accounts.models import AccountSnapshot
from packages.shared.domain_types import utc_now


def validate_snapshot(
    snapshot: AccountSnapshot, expected_account_id: UUID, max_age: timedelta = timedelta(seconds=30)
) -> None:
    if snapshot.account_id != expected_account_id:
        raise ValueError("snapshot belongs to a different account")
    if utc_now() - snapshot.observed_at > max_age:
        raise ValueError("account snapshot is stale")
    if snapshot.current_equity <= 0:
        raise ValueError("current equity must be positive")
