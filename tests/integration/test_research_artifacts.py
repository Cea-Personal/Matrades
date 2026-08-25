from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from modules.research.artifacts import ResearchCycleArchive


def test_market_and_strategy_cycles_get_timestamped_immutable_folders(tmp_path) -> None:
    archive = ResearchCycleArchive(tmp_path)
    owner_id = uuid4()
    observed_at = datetime(2026, 8, 25, 8, 30, tzinfo=UTC)

    market = archive.save_cycle(
        owner_id=owner_id,
        cycle_type="market_research",
        cycle_id=uuid4(),
        occurred_at=observed_at,
        details={"state": "MARKETS_PENDING_APPROVAL", "candidates": ["EUR/USD"]},
    )
    strategy = archive.save_cycle(
        owner_id=owner_id,
        cycle_type="strategy_research",
        cycle_id=uuid4(),
        occurred_at=observed_at,
        details={"state": "AWAITING_STRATEGY_APPROVAL", "family": "TREND"},
    )

    assert market.relative_path.startswith(f"{owner_id}/market_research/2026/08/25/")
    assert strategy.relative_path.startswith(f"{owner_id}/strategy_research/2026/08/25/")
    manifest = json.loads((tmp_path / market.relative_path / "manifest.json").read_text())
    assert manifest["occurred_at"] == observed_at.isoformat()
    assert manifest["checksum"] == market.checksum
    assert market.relative_path != strategy.relative_path
