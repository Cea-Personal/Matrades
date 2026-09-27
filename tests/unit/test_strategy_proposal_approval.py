from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.app.routes import strategies
from modules.identity.authorization import Actor, Role
from tests.integration.test_strategy_generation import strategy


@pytest.mark.parametrize(
    "action,state,stage",
    [
        ("APPROVE", "DRAFT", "WAITING_FOR_VERSION"),
        ("REJECT", "REJECTED", "BLOCKED"),
    ],
)
async def test_proposal_decision_records_human_choice_without_live_approval(
    monkeypatch,
    action,
    state,
    stage,
):
    draft_id = uuid4()
    actor = Actor(actor_id=uuid4(), owner_id=uuid4(), role=Role.OWNER)
    draft = SimpleNamespace(
        id=draft_id,
        state="AWAITING_STRATEGY_APPROVAL",
        data={
            "proposed_specification": {**strategy("Test"), "origin": "AI_GENERATED"},
            "strategy_pipeline": {"stages": {"preliminary_backtest": "COMPLETED"}},
        },
    )

    class Store:
        def __init__(self, db):
            pass

        async def get(self, kind, record_id, owner_id):
            assert kind == "strategy_draft"
            assert record_id == draft_id
            assert owner_id == actor.owner_id
            return draft

        async def update(self, record, data, **kwargs):
            record.data = data
            record.state = kwargs["state"]
            return SimpleNamespace(public=lambda: {"state": record.state, **data})

    monkeypatch.setattr(strategies, "ResourceStore", Store)
    result = await strategies.decide_strategy_proposal(
        draft_id,
        strategies.StrategyProposalDecision(action=action),
        actor,
        None,
    )
    assert result["state"] == state
    assert result["state"] != "APPROVED"
    assert result["strategy_pipeline"]["stages"]["formal_backtest"] == stage
    assert result["strategy_pipeline"]["stages"]["preliminary_backtest"] == "COMPLETED"
    assert result["provenance"]["decision_actor_id"] == str(actor.actor_id)


async def test_only_awaiting_proposals_can_be_decided(monkeypatch):
    class Store:
        def __init__(self, db):
            pass

        async def get(self, *args):
            return SimpleNamespace(state="REJECTED")

    monkeypatch.setattr(strategies, "ResourceStore", Store)
    actor = Actor(actor_id=uuid4(), owner_id=uuid4(), role=Role.OWNER)
    with pytest.raises(HTTPException) as error:
        await strategies.decide_strategy_proposal(
            uuid4(),
            strategies.StrategyProposalDecision(action="APPROVE"),
            actor,
            None,
        )
    assert error.value.status_code == 409
