from uuid import uuid4

from modules.strategies.drafts import DraftRepository
from packages.strategy_sdk.taxonomy import StrategyOrigin


def test_all_origins_create_same_draft_shape():
    repo = DraftRepository()
    items = [repo.create(uuid4(), origin) for origin in StrategyOrigin]
    assert {set(x.model_dump()) for x in []} == set()
    assert len(items) == 4
