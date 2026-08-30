from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from adapters.broker.mt5_bridge.client import Mt5BridgeClient
from apps.worker.app.celery_app import celery_app
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection
from modules.risk.reservations import PersistentReservationStore, ReservationState
from modules.trading.authority import assert_command_authority
from modules.trading.coordinator import (
    authorize_and_queue_entry,
    current_broker_snapshot,
    current_kill_switches,
    current_permissions,
)
from modules.trading.execution import ExecutionService
from modules.trading.execution_store import lease_command
from modules.trading.models import CommandState, ExecutionCommand, TradePlan, TradePlanState
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore


async def _lease(owner_id: UUID, command_id: UUID, worker_id: str) -> dict:
    async with unit_of_work() as session:
        record = await lease_command(
            ResourceStore(session),
            owner_id=owner_id,
            command_id=command_id,
            worker_id=worker_id,
        )
        return {"command_id": str(command_id), "leased": record is not None}


async def _queue_plan(owner_id: UUID, plan_id: UUID) -> dict:
    async with unit_of_work() as session:
        record = await ResourceStore(session).get("trade_plan", plan_id, owner_id)
        if record is None:
            raise RuntimeError("trade plan not found")
        plan = TradePlan.model_validate(record.data)
        plan_record, command_record = await authorize_and_queue_entry(session, plan)
        return {
            "trade_plan_id": str(plan_record.id),
            "state": plan_record.state,
            "command_id": str(command_record.id) if command_record else None,
        }


async def _dispatch(owner_id: UUID, command_id: UUID, worker_id: str) -> dict:
    async with unit_of_work() as session:
        command_record = await session.scalar(
            select(ResourceRecord)
            .where(
                ResourceRecord.id == command_id,
                ResourceRecord.kind == "execution_command",
                ResourceRecord.owner_id == owner_id,
            )
            .with_for_update()
        )
        if command_record is None:
            raise RuntimeError("execution command not found")
        if command_record.state in {
            CommandState.ACKNOWLEDGED.value,
            CommandState.APPLIED.value,
            CommandState.REJECTED.value,
            CommandState.BLOCKED_AMBIGUOUS.value,
        }:
            return {"command_id": str(command_id), "state": command_record.state, "replayed": True}
        command = ExecutionCommand.model_validate(command_record.data)
        if command.trade_plan_id is None:
            raise RuntimeError("execution command has no Trade Plan")
        plan_record = await session.scalar(
            select(ResourceRecord)
            .where(
                ResourceRecord.id == command.trade_plan_id,
                ResourceRecord.kind == "trade_plan",
                ResourceRecord.owner_id == owner_id,
            )
            .with_for_update()
        )
        if plan_record is None:
            raise RuntimeError("execution command Trade Plan not found")
        plan = TradePlan.model_validate(plan_record.data)
        if plan.authorization is None:
            raise RuntimeError("execution authorization is unavailable")
        await current_broker_snapshot(session, owner_id, command.account_id)
        permissions = await current_permissions(session, owner_id, command.account_id, lock=True)
        platform_kill, account_kill = await current_kill_switches(
            session, owner_id, command.account_id, lock=True
        )
        assert_command_authority(
            command, plan.authorization, plan, permissions, platform_kill, account_kill
        )
        leased = await lease_command(
            ResourceStore(session),
            owner_id=owner_id,
            command_id=command_id,
            worker_id=worker_id,
        )
        if leased is None:
            return {"command_id": str(command_id), "state": command_record.state, "leased": False}
        command = ExecutionCommand.model_validate(leased.data)
        connection = await find_connection(session, owner_id, ConnectionProvider.MT5_BRIDGE)
        if connection is None or connection.secret is None:
            raise RuntimeError("active MT5 Bridge connection and HMAC secret are required")
        bridge_url = str(connection.profile.configuration.get("bridge_url", ""))
        adapter = Mt5BridgeClient(bridge_url, connection.secret.encode())
        try:
            outcome = await ExecutionService().dispatch(command, plan.authorization, adapter)
        finally:
            await adapter.close()
        updated = await ResourceStore(session).update(
            leased,
            {**outcome.model_dump(mode="json"), "lease": leased.data.get("lease")},
            state=outcome.state.value,
            event_type=f"execution.command.{outcome.state.value.lower()}",
            evidence={
                "outcome_certainty": outcome.outcome_certainty.value,
                "broker_order_id": outcome.broker_order_id,
            },
        )
        if plan.reservation_id is not None:
            reservations = PersistentReservationStore(session)
            if outcome.state is CommandState.REJECTED:
                await reservations.transition(
                    plan.reservation_id,
                    owner_id=owner_id,
                    target=ReservationState.RELEASED,
                    reason="broker rejected command",
                )
            elif outcome.state is CommandState.ACKNOWLEDGED:
                await reservations.transition(
                    plan.reservation_id,
                    owner_id=owner_id,
                    target=ReservationState.ORDER_WORKING,
                    broker_order_id=outcome.broker_order_id,
                )
        if (
            outcome.state is CommandState.ACKNOWLEDGED
            and plan.state is TradePlanState.EXECUTION_PENDING
        ):
            plan.state = TradePlanState.EXECUTING
            plan.version += 1
            await ResourceStore(session).update(
                plan_record,
                plan.model_dump(mode="json"),
                state=plan.state.value,
                event_type="trade_plan.executing",
            )
        return {"command_id": str(updated.id), "state": updated.state, "leased": True}


@celery_app.task(name="apps.worker.app.tasks.execution.lease_execution_command")
def lease_execution_command(
    owner_id: str, command_id: str, worker_id: str = "execution-worker"
) -> dict:
    return asyncio.run(_lease(UUID(owner_id), UUID(command_id), worker_id))


@celery_app.task(name="apps.worker.app.tasks.execution.queue_trade_plan_execution")
def queue_trade_plan_execution(owner_id: str, plan_id: str) -> dict:
    result = asyncio.run(_queue_plan(UUID(owner_id), UUID(plan_id)))
    if result.get("command_id"):
        dispatch_execution_command.delay(owner_id, str(result["command_id"]))
    return result


@celery_app.task(name="apps.worker.app.tasks.execution.dispatch_execution_command")
def dispatch_execution_command(
    owner_id: str, command_id: str, worker_id: str = "execution-worker"
) -> dict:
    return asyncio.run(_dispatch(UUID(owner_id), UUID(command_id), worker_id))
