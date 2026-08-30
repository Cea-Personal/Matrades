from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from modules.risk.engine import RiskEngine
from modules.trading.execution import CommandConflict, ExecutionService
from modules.trading.models import (
    CommandState,
    ExecutionPermissionProfile,
    KillSwitchState,
    TradeConstruction,
    TradePlan,
    TradePlanState,
)
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit, utc_now
from tests.fixtures.pretrade import candidate, context


def make_plan() -> TradePlan:
    risk = RiskEngine().evaluate(context(), candidate())
    return TradePlan(
        owner_id=uuid4(),
        account_id=risk.snapshot.account_id,
        state=TradePlanState.READY,
        construction=TradeConstruction(
            instrument="EURUSD",
            direction=candidate().direction,
            entry=Decimal("1.085"),
            stop_loss=Decimal("1.08"),
            targets=[Decimal("1.095")],
            invalidation="close below stop",
            approved_size=risk.approved_size,
            quantity_unit=QuantityUnit.LOTS,
            asset_class=AssetClass.FOREX,
            instrument_type=InstrumentType.CFD,
            venue_instrument_id=uuid4(),
            specification_version_id=uuid4(),
        ),
        strategy_version_id=uuid4(),
        market_fingerprint_id=uuid4(),
        risk=risk,
        expires_at=utc_now() + timedelta(minutes=5),
    )


class RecordingAdapter:
    async def submit_order(self, command, authorization):
        return {"confirmed": True, "broker_order_id": "broker-1"}


class FailingAdapter:
    async def submit_order(self, command, authorization):
        raise TimeoutError("broker timeout")


def permissions(account_id):
    return ExecutionPermissionProfile(account_id=account_id, new_entry=True)


def switches():
    return KillSwitchState(scope="PLATFORM"), KillSwitchState(scope="ACCOUNT")


def test_authorization_requires_enabled_permission():
    plan = make_plan()
    with pytest.raises(PermissionError):
        ExecutionService().authorize(
            plan, ExecutionPermissionProfile(account_id=plan.account_id), *switches()
        )


@pytest.mark.asyncio
async def test_dispatch_is_idempotent_and_confirms_broker_outcome():
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    command = service.create_command(plan, authorization, idempotency_key="entry-eurusd-1")
    duplicate = service.create_command(
        plan, authorization, idempotency_key="entry-eurusd-1"
    )
    assert duplicate.id == command.id
    assert service.ledger.outbox[0]["event_type"] == "execution.command.created"
    applied = await service.dispatch(command, authorization, RecordingAdapter())

    assert applied.state == CommandState.ACKNOWLEDGED
    assert applied.broker_order_id == "broker-1"
    assert applied.outcome_certainty.value == "CONFIRMED"


def test_idempotency_rejects_changed_postcondition():
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    service.create_command(plan, authorization, idempotency_key="entry-eurusd-2")
    changed = plan.model_copy(deep=True)
    changed.construction.approved_size = Decimal("999")
    with pytest.raises(CommandConflict):
        service.create_command(changed, authorization, idempotency_key="entry-eurusd-2")


@pytest.mark.asyncio
async def test_transport_failure_is_explicitly_uncertain():
    plan = make_plan()
    service = ExecutionService()
    authorization = service.authorize(plan, permissions(plan.account_id), *switches())
    command = service.create_command(plan, authorization, idempotency_key="entry-eurusd-3")
    outcome = await service.dispatch(command, authorization, FailingAdapter())

    assert outcome.state == CommandState.OUTCOME_UNKNOWN
    assert outcome.outcome_certainty.value == "UNCERTAIN"
