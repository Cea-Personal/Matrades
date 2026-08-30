from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from modules.strategies.evidence import resolve_approved_candidate


def test_stale_market_evidence_cannot_feed_strategy_research() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="unavailable"):
        resolve_approved_candidate(
            {"selected": {"FOREX": "EURUSD"}},
            {"account_id": str(uuid4()), "candidates": []},
            now=now,
            max_age=timedelta(hours=1),
        )
