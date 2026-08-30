from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.execution import dispatch_execution_command
from modules.identity.authorization import Actor, Role
from modules.notifications.service import queue_confirmed_broker_notifications
from modules.risk.reservations import PersistentReservationStore, ReservationState
from modules.trading.broker_models import (
    ActiveTrade,
    ManagementRecommendation,
    RecommendationAction,
)
from modules.trading.charts import authoritative_chart
from modules.trading.coordinator import authorize_and_queue_management
from modules.trading.hil3 import Hil3Action
from modules.trading.models import (
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    CommandState,
    ExecutionAction,
    ExecutionCommand,
    TradePlan,
    TradePlanState,
)
from modules.trading.monitor import monitoring_facts
from modules.trading.monitor_agent import interpret
from modules.trading.reconciliation import reconcile_command
from modules.trading.trade_plans import transition_trade_plan
from packages.broker_sdk.schemas import BrokerSnapshot
from packages.shared.domain_types import OutcomeCertainty, utc_now
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/trade-management", tags=["Trade management"])


class MonitoringInput(BaseModel):
    trade_id: UUID
    current_price: Decimal
    bridge_fresh: bool = True


class RecommendationInput(BaseModel):
    action: RecommendationAction
    reason: str
    proposed_value: Decimal | None = None


class DecisionInput(BaseModel):
    action: Hil3Action
    reason: str | None = None


class ManagementActionInput(BaseModel):
    trade_plan_id: UUID
    action: ExecutionAction
    requested_postcondition: dict
    target_order_id: str | None = None
    target_position_id: str | None = None
    expected_broker_version: str | None = None
    reason: str = "deterministic trade-monitor action"


@router.post("/broker-snapshots", status_code=status.HTTP_202_ACCEPTED)
async def ingest_broker_snapshot(
    snapshot: BrokerSnapshot,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    existing_snapshots = [
        item
        for item in await store.list("broker_snapshot", actor.owner_id)
        if item.data.get("account_id") == str(snapshot.account_id)
    ]
    duplicate = next(
        (
            item
            for item in existing_snapshots
            if item.data.get("message_id") == str(snapshot.message_id)
        ),
        None,
    )
    if duplicate is not None:
        return {"sequence": snapshot.sequence, "reconciliations": [], "duplicate": True}
    if existing_snapshots and snapshot.sequence <= int(
        existing_snapshots[0].data.get("sequence", -1)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "out-of-order or replayed broker snapshot")
    await store.create(
        "broker_snapshot",
        actor.owner_id,
        snapshot.model_dump(mode="json"),
        actor_id=actor.actor_id,
        event_type="broker.account_changed",
    )
    typed_positions = [
        BrokerPosition(
            account_id=item.account_id,
            broker_position_id=item.position_id,
            instrument=item.symbol,
            direction=item.direction.value,
            quantity=item.volume,
            average_price=item.entry_price,
            version=snapshot.sequence,
            observed_at=item.observed_at,
            asset_class=item.asset_class,
            instrument_type=item.instrument_type,
            venue_instrument_id=item.venue_instrument_id,
            futures_contract_id=item.futures_contract_id,
            specification_version_id=item.specification_version_id,
            quantity_unit=item.quantity_unit,
        )
        for item in snapshot.positions
    ]
    reconciliations: list[dict] = []
    pending_states = {
        CommandState.DISPATCHING.value,
        CommandState.ACKNOWLEDGED.value,
        CommandState.PARTIALLY_APPLIED.value,
        CommandState.OUTCOME_UNKNOWN.value,
        CommandState.RECONCILING.value,
    }
    for command_record in await store.list("execution_command", actor.owner_id):
        if command_record.state not in pending_states:
            continue
        command = ExecutionCommand.model_validate(command_record.data)
        if command.account_id != snapshot.account_id:
            continue
        relevant_orders = [
            BrokerOrder(
                account_id=item.account_id,
                command_id=command.id,
                broker_order_id=item.order_id,
                instrument=item.symbol,
                direction=item.direction.value,
                state=item.state,
                quantity=item.requested_volume,
                filled_quantity=item.filled_volume,
                version=item.version,
                observed_at=item.observed_at,
                asset_class=item.asset_class,
                instrument_type=item.instrument_type,
                venue_instrument_id=item.venue_instrument_id,
                futures_contract_id=item.futures_contract_id,
                specification_version_id=item.specification_version_id,
                quantity_unit=item.quantity_unit,
            )
            for item in snapshot.orders
            if item.command_id == command.id
            or (command.broker_order_id is not None and item.order_id == command.broker_order_id)
        ]
        result = reconcile_command(
            command,
            relevant_orders,
            typed_positions,
            authoritative_snapshot=True,
        )
        reconciliation_record = await store.create(
            "reconciliation",
            actor.owner_id,
            result.model_dump(mode="json"),
            state=result.state,
            actor_id=actor.actor_id,
            event_type=(
                "reconciliation.confirmed"
                if result.state == "MATCHED"
                else "reconciliation.ambiguous"
                if result.state == "AMBIGUOUS"
                else "reconciliation.no_effect_confirmed"
            ),
        )
        reconciliations.append(reconciliation_record.public())
        if result.state == "AMBIGUOUS":
            command = command.model_copy(
                update={
                    "state": CommandState.BLOCKED_AMBIGUOUS,
                    "outcome_certainty": OutcomeCertainty.UNCERTAIN,
                    "version": command.version + 1,
                }
            )
            await store.update(
                command_record,
                command.model_dump(mode="json"),
                state=command.state.value,
                actor_id=actor.actor_id,
                event_type="execution.command.blocked_ambiguous",
            )
            continue
        if result.state == "NO_EFFECT_CONFIRMED":
            command = command.model_copy(
                update={
                    "state": CommandState.NO_EFFECT_CONFIRMED,
                    "outcome_certainty": OutcomeCertainty.CONFIRMED,
                    "version": command.version + 1,
                }
            )
            await store.update(
                command_record,
                command.model_dump(mode="json"),
                state=command.state.value,
                actor_id=actor.actor_id,
                event_type="execution.command.no_effect_confirmed",
            )
            continue
        if command.trade_plan_id is None:
            continue
        plan_record = await store.get("trade_plan", command.trade_plan_id, actor.owner_id)
        if plan_record is None:
            continue
        plan = TradePlan.model_validate(plan_record.data)
        matched_order = relevant_orders[0] if len(relevant_orders) == 1 else None
        matched_position = next(
            (
                item
                for item in snapshot.positions
                if item.position_id == result.broker_position_id
            ),
            None,
        )
        fills = [
            BrokerFill(
                account_id=item.account_id,
                broker_order_id=item.order_id,
                broker_fill_id=item.fill_id,
                quantity=item.quantity,
                price=item.price,
                revision=item.revision,
                observed_at=item.observed_at,
            )
            for item in snapshot.fills
            if matched_order is not None and item.order_id == matched_order.broker_order_id
        ]
        for order in relevant_orders:
            existing_orders = [
                item
                for item in await store.list("broker_order", actor.owner_id)
                if item.data.get("broker_order_id") == order.broker_order_id
                and int(item.data.get("version", 0)) == order.version
            ]
            if not existing_orders:
                await store.create(
                    "broker_order",
                    actor.owner_id,
                    order.model_dump(mode="json"),
                    state=order.state,
                    actor_id=actor.actor_id,
                    event_type="broker.order_reconciled",
                )
        for fill in fills:
            existing_fills = [
                item
                for item in await store.list("broker_fill", actor.owner_id)
                if item.data.get("broker_fill_id") == fill.broker_fill_id
                and int(item.data.get("revision", 0)) == fill.revision
            ]
            if not existing_fills:
                await store.create(
                    "broker_fill",
                    actor.owner_id,
                    fill.model_dump(mode="json"),
                    actor_id=actor.actor_id,
                    event_type="broker.fill_reconciled",
                )
        requested_quantity = Decimal(str(command.requested_postcondition.get("quantity", "0")))
        filled_quantity = (
            matched_order.filled_quantity
            if matched_order is not None
            else abs(matched_position.volume) if matched_position is not None else Decimal("0")
        )
        next_state = (
            CommandState.APPLIED
            if filled_quantity > 0 and filled_quantity >= requested_quantity
            else CommandState.PARTIALLY_APPLIED
            if filled_quantity > 0
            else CommandState.ACKNOWLEDGED
        )
        command = command.model_copy(
            update={
                "state": next_state,
                "outcome_certainty": OutcomeCertainty.CONFIRMED,
                "broker_order_id": (
                    matched_order.broker_order_id if matched_order else command.broker_order_id
                ),
                "version": command.version + 1,
            }
        )
        await store.update(
            command_record,
            command.model_dump(mode="json"),
            state=command.state.value,
            actor_id=actor.actor_id,
            event_type=f"execution.command.{command.state.value.lower()}",
        )
        if command.action is ExecutionAction.PLACE_ORDER and matched_position is not None:
            active_records = await store.list("active_trade", actor.owner_id)
            active_record = next(
                (
                    item
                    for item in active_records
                    if item.data.get("broker_position", {}).get("position_id")
                    == matched_position.position_id
                ),
                None,
            )
            active = ActiveTrade(
                owner_id=actor.owner_id,
                trade_plan_id=plan.id,
                execution_command_id=command.id,
                broker_position=matched_position,
                asset_class=plan.construction.asset_class,
                instrument_type=plan.construction.instrument_type,
                quantity_unit=plan.construction.quantity_unit,
            )
            if active_record is None:
                await store.create(
                    "active_trade",
                    actor.owner_id,
                    active.model_dump(mode="json"),
                    state=active.state.value,
                    record_id=active.id,
                    actor_id=actor.actor_id,
                    event_type="trade.position_activated",
                )
            else:
                await store.update(
                    active_record,
                    {**active.model_dump(mode="json"), "id": str(active_record.id)},
                    state=active.state.value,
                    actor_id=actor.actor_id,
                    event_type="trade.position_revised",
                )
            if plan.state is TradePlanState.EXECUTING:
                plan = transition_trade_plan(plan, TradePlanState.ACTIVE)
                await store.update(
                    plan_record,
                    plan.model_dump(mode="json"),
                    state=plan.state.value,
                    actor_id=actor.actor_id,
                    event_type="trade_plan.active",
                )
            if plan.reservation_id is not None:
                reserved_risk = plan.risk.snapshot.candidate_trade_risk
                if requested_quantity > 0 and filled_quantity < requested_quantity:
                    filled_risk = reserved_risk * filled_quantity / requested_quantity
                    await PersistentReservationStore(db).split_partial_fill(
                        plan.reservation_id,
                        owner_id=actor.owner_id,
                        filled_amount=filled_risk,
                        broker_position_id=matched_position.position_id,
                        remaining_command_amount=reserved_risk - filled_risk,
                    )
                else:
                    await PersistentReservationStore(db).transition(
                        plan.reservation_id,
                        owner_id=actor.owner_id,
                        target=ReservationState.OPEN_POSITION,
                        broker_position_id=matched_position.position_id,
                    )
        if matched_order is not None:
            await queue_confirmed_broker_notifications(
                db,
                owner_id=actor.owner_id,
                command_id=command.id,
                event_kind=(
                    "trade_entry_complete"
                    if command.state is CommandState.APPLIED
                    else "trade_entry_partial"
                    if command.state is CommandState.PARTIALLY_APPLIED
                    else "order_accepted"
                ),
                revision=max(
                    [matched_order.version, *(item.revision for item in fills)]
                ),
                account_id=command.account_id,
                instrument=matched_order.instrument,
                quantity=filled_quantity or matched_order.quantity,
                price=(fills[-1].price if fills else None),
                stop_loss=plan.construction.stop_loss,
                take_profit=plan.construction.targets[0],
                strategy_version_id=plan.strategy_version_id,
                trade_plan_id=plan.id,
                broker_order_id=matched_order.broker_order_id,
                observed_at=matched_order.observed_at,
            )
    return {"sequence": snapshot.sequence, "reconciliations": reconciliations}


@router.get("/reconciliations")
async def list_reconciliations(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("reconciliation", actor.owner_id)
    return [item.public() for item in records]


@router.get("/trades")
async def list_trades(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("active_trade", actor.owner_id)
    return [item.public() for item in records]


@router.get("/trades/{trade_id}/chart")
async def trade_chart(
    trade_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    timeframe: str = "1h",
):
    record = await ResourceStore(db).get("active_trade", trade_id, actor.owner_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active trade not found")
    position = record.data.get("broker_position", {})
    instrument = str(position.get("instrument", record.data.get("instrument", "UNKNOWN")))
    return (
        await authoritative_chart(
            ResourceStore(db),
            owner_id=actor.owner_id,
            trade_id=trade_id,
            instrument=instrument,
            timeframe=timeframe,
            trade_plan_id=(
                UUID(str(record.data["trade_plan_id"]))
                if record.data.get("trade_plan_id")
                else None
            ),
        )
    ).model_dump(mode="json")


@router.post("/monitor")
async def monitor_trade(
    payload: MonitoringInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    trade_record = await store.get("active_trade", payload.trade_id, actor.owner_id)
    if trade_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active trade not found")
    trade = ActiveTrade.model_validate(trade_record.data)
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    facts = monitoring_facts(trade, payload.current_price, policy_valid, payload.bridge_fresh)
    recommendation = interpret(trade.id, facts)
    item = await store.create(
        "management_recommendation",
        actor.owner_id,
        {**recommendation.model_dump(mode="json"), "policy_valid": policy_valid, "facts": facts},
        state="AUTHORIZATION_REQUIRED" if recommendation.requires_authorization else "HOLD",
        record_id=recommendation.id,
        actor_id=actor.actor_id,
        event_type="trade.monitoring_updated",
    )
    return item.public()


@router.post("/trades/{trade_id}/recommendations", status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    trade_id: UUID,
    payload: RecommendationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    trade = await store.get("active_trade", trade_id, actor.owner_id)
    if trade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active trade not found")
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    recommendation = ManagementRecommendation(
        trade_id=trade_id,
        action=payload.action,
        reason=payload.reason,
        proposed_value=payload.proposed_value,
        requires_authorization=payload.action != RecommendationAction.HOLD,
    )
    item = await store.create(
        "management_recommendation",
        actor.owner_id,
        {**recommendation.model_dump(mode="json"), "policy_valid": policy_valid},
        state="QUEUING" if recommendation.requires_authorization else "HOLD",
        record_id=recommendation.id,
        actor_id=actor.actor_id,
        event_type=(
            "trade_management.action_selected"
            if recommendation.requires_authorization
            else "trade.monitoring_updated"
        ),
    )
    if not recommendation.requires_authorization:
        return item.public()
    active = ActiveTrade.model_validate(trade.data)
    if active.trade_plan_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "active trade has no Trade Plan")
    plan_record = await store.get("trade_plan", active.trade_plan_id, actor.owner_id)
    if plan_record is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "active Trade Plan is unavailable")
    plan = TradePlan.model_validate(plan_record.data)
    action = {
        RecommendationAction.MOVE_SL: ExecutionAction.SET_OR_CHANGE_STOP_LOSS,
        RecommendationAction.PARTIAL_TP: ExecutionAction.PARTIAL_CLOSE,
        RecommendationAction.EARLY_EXIT: ExecutionAction.FULL_EXIT,
        RecommendationAction.FULL_EXIT: ExecutionAction.FULL_EXIT,
    }[payload.action]
    postcondition = (
        {"stop_loss": str(payload.proposed_value)}
        if action is ExecutionAction.SET_OR_CHANGE_STOP_LOSS
        else {"quantity": str(payload.proposed_value)}
        if action is ExecutionAction.PARTIAL_CLOSE
        else {"position_state": "CLOSED"}
    )
    command_record = await authorize_and_queue_management(
        db,
        owner_id=actor.owner_id,
        plan=plan,
        action=action,
        postcondition=postcondition,
        idempotency_key=f"monitor:{item.id}:{action.value}",
        management_action_id=item.id,
        target_position_id=active.broker_position.position_id,
        expected_broker_version=str(active.broker_position.observed_at.isoformat()),
    )
    item = await store.update(
        item,
        {
            **item.data,
            "execution_command_id": str(command_record.id),
            "authorization_required": False,
        },
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="trade_management.command_queued",
    )
    response = item.public()
    await db.commit()
    dispatch_execution_command.delay(str(actor.owner_id), str(command_record.id))
    return response


@router.post("/actions", status_code=status.HTTP_202_ACCEPTED)
async def queue_management_action(
    payload: ManagementActionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if payload.action is ExecutionAction.PLACE_ORDER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "entry uses Trade Plans")
    store = ResourceStore(db)
    plan_record = await store.get("trade_plan", payload.trade_plan_id, actor.owner_id)
    if plan_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trade Plan not found")
    plan = TradePlan.model_validate(plan_record.data)
    action_id = uuid5(
        NAMESPACE_URL,
        f"{actor.owner_id}:{plan.id}:{payload.action.value}:"
        f"{payload.target_order_id}:{payload.target_position_id}:"
        f"{payload.expected_broker_version}:{payload.requested_postcondition}",
    )
    recommendation = await store.create(
        "management_recommendation",
        actor.owner_id,
        {
            "trade_plan_id": str(plan.id),
            "action": payload.action.value,
            "reason": payload.reason,
            "requested_postcondition": payload.requested_postcondition,
            "target_order_id": payload.target_order_id,
            "target_position_id": payload.target_position_id,
        },
        state="QUEUING",
        record_id=action_id,
        actor_id=actor.actor_id,
        event_type="trade_management.action_selected",
    )
    command_record = await authorize_and_queue_management(
        db,
        owner_id=actor.owner_id,
        plan=plan,
        action=payload.action,
        postcondition=payload.requested_postcondition,
        idempotency_key=f"management:{action_id}",
        management_action_id=action_id,
        target_order_id=payload.target_order_id,
        target_position_id=payload.target_position_id,
        expected_broker_version=payload.expected_broker_version,
    )
    await store.update(
        recommendation,
        {**recommendation.data, "execution_command_id": str(command_record.id)},
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="trade_management.command_queued",
    )
    response = command_record.public()
    await db.commit()
    dispatch_execution_command.delay(str(actor.owner_id), str(command_record.id))
    return response


@router.get("/recommendations")
async def list_recommendations(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("management_recommendation", actor.owner_id)
    return [item.public() for item in records]


@router.post("/recommendations/{recommendation_id}/decisions")
async def hil3_decision(
    recommendation_id: UUID,
    payload: DecisionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raise HTTPException(status.HTTP_410_GONE, "manual management decisions are retired")
    store = ResourceStore(db)
    item = await store.get("management_recommendation", recommendation_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    if item.state != "ACTION_REQUIRED":
        raise HTTPException(status.HTTP_409_CONFLICT, "recommendation is not awaiting HIL-3")
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    if payload.action == Hil3Action.APPROVE and not policy_valid:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "recommendation no longer complies with policy"
        )
    next_state = {
        Hil3Action.APPROVE: "APPROVED_MANUAL_ACTION",
        Hil3Action.WAIT: "WAITING",
        Hil3Action.REJECT: "REJECTED",
    }[payload.action]
    updated = await store.update(
        item,
        {
            **item.data,
            "decision": payload.action,
            "decision_reason": payload.reason,
            "decided_at": utc_now().isoformat(),
            "broker_mutated": False,
            "manual_execution_required": payload.action == Hil3Action.APPROVE,
        },
        state=next_state,
        actor_id=actor.actor_id,
        event_type=f"trade_management.{payload.action.value.lower()}",
    )
    return updated.public()
