from uuid import uuid4

import pytest

from traderx.identity.authorization import Actor, Role
from traderx.instruments.active_markets import ActiveMarketRegistry
from traderx.shared.types import ConcurrentModification


def test_research_cannot_silently_replace_active_market() -> None:
    registry = ActiveMarketRegistry()
    actor = Actor(Role.OWNER, "MFA", uuid4())
    original = registry.activate(
        actor, category="COMMODITY", instrument_id=uuid4(), expected_version=None, replace=False
    )
    with pytest.raises(ConcurrentModification):
        registry.activate(
            actor,
            category="COMMODITY",
            instrument_id=uuid4(),
            expected_version=original.version,
            replace=False,
        )
