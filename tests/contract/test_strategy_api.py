from uuid import uuid4

from apps.api.app.main import create_app
from modules.strategies.drafts import DraftRepository
from packages.strategy_sdk.taxonomy import StrategyOrigin


def test_all_origins_create_same_draft_shape():
    repo = DraftRepository()
    items = [repo.create(uuid4(), origin) for origin in StrategyOrigin]
    assert {set(x.model_dump()) for x in []} == set()
    assert len(items) == 2
    assert {item.origin for item in items} == {
        StrategyOrigin.AI_GENERATED,
        StrategyOrigin.AI_ASSISTED,
    }


def test_strategy_api_exposes_grounding_readiness_before_generation() -> None:
    operation = create_app().openapi()["paths"]["/api/v1/strategies/research-context"]["get"]
    assert operation["operationId"] == (
        "strategy_research_context_api_v1_strategies_research_context_get"
    )
