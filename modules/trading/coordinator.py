"""Transactional application boundary for autonomous Trade Plan execution."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.accounts.models import AccountSnapshot
from modules.accounts.snapshots import validate_snapshot
from modules.risk.authority import authoritative_risk_context
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, RiskDecision
from modules.risk.reservations import PersistentReservationStore, ReservationState
from modules.trading.execution import ExecutionService, transition
from modules.trading.execution_store import persist_command
from modules.trading.models import (
    CommandState,
    ExecutionAction,
    ExecutionPermissionProfile,
    KillSwitchState,
    TradePlan,
    TradePlanState,
)
from modules.trading.trade_plans import transition_trade_plan
from packages.broker_sdk.schemas import BrokerSnapshot
from packages.shared.store import ResourceRecord, ResourceStore


async def current_permissions(
    session: AsyncSession, owner_id: UUID, account_id: UUID, *, lock: bool = False
) -> ExecutionPermissionProfile:
    statement = (
        select(ResourceRecord)
        .where(
            ResourceRecord.kind == "execution_permission_profile",
            ResourceRecord.owner_id == owner_id,
            ResourceRecord.state != "DELETED",
        )
        .order_by(ResourceRecord.updated_at.desc())
    )
    if lock:
        statement = statement.with_for_update()
    records = list((await session.scalars(statement)).all())
    for record in records:
        if record.data.get("account_id") == str(account_id):
            return ExecutionPermissionProfile.model_validate(record.data)
    return ExecutionPermissionProfile(
        account_id=account_id,
        reason="no explicit execution permission profile configured",
    )


async def current_kill_switches(
    session: AsyncSession, owner_id: UUID, account_id: UUID, *, lock: bool = False
) -> tuple[KillSwitchState, KillSwitchState]:
    statement = select(ResourceRecord).where(
        ResourceRecord.owner_id == owner_id,
        ResourceRecord.kind.in_(("platform_kill_switch", "account_kill_switch")),
        ResourceRecord.state != "DELETED",
    )
    if lock:
        statement = statement.with_for_update()
    records = list((await session.scalars(statement)).all())
    platform = KillSwitchState(scope="PLATFORM")
    account = KillSwitchState(scope="ACCOUNT", account_id=account_id)
    for record in sorted(records, key=lambda item: item.updated_at):
        if record.kind == "platform_kill_switch":
            platform = KillSwitchState.model_validate(record.data)
        elif record.data.get("account_id") == str(account_id):
            account = KillSwitchState.model_validate(record.data)
    return platform, account


async def current_broker_snapshot(
    session: AsyncSession, owner_id: UUID, account_id: UUID
) -> BrokerSnapshot:
    records = [
        record
        for record in await ResourceStore(session).list("broker_snapshot", owner_id)
        if record.data.get("account_id") == str(account_id)
    ]
    if not records:
        raise PermissionError("fresh broker snapshot is required")
    snapshot = BrokerSnapshot.model_validate(records[0].data)
    account_snapshot = AccountSnapshot(
        account_id=account_id,
        starting_balance=snapshot.balance,
        current_balance=snapshot.balance,
        current_equity=snapshot.equity,
        floating_pnl=snapshot.equity - snapshot.balance,
        realized_daily_pnl=snapshot.realized_daily_pnl,
        observed_at=snapshot.observed_at,
        source="MT5_BRIDGE",
        source_version=f"sequence:{snapshot.sequence}",
        broker_sequence=snapshot.sequence,
    )
    validate_snapshot(account_snapshot, account_id)
    return snapshot


async def _typed_candidate(session: AsyncSession, plan: TradePlan) -> CandidateTrade:
    records = await ResourceStore(session).list("typed_instrument", plan.owner_id)
    specification: dict | None = None
    for record in records:
        raw = record.data.get("specification", record.data)
        if str(raw.get("id") or record.data.get("specification_version_id")) == str(
            plan.construction.specification_version_id
        ):
            specification = raw
            break
    if specification is None or str(specification.get("freshness", "INVALID")) != "VALID":
        raise PermissionError("fresh effective instrument specification is required")
    risk_amount = plan.risk.snapshot.candidate_trade_risk
    size = plan.construction.approved_size
    risk_per_unit = risk_amount / size if risk_amount > 0 else abs(
        plan.construction.entry - plan.construction.stop_loss
    )
    if risk_per_unit <= 0:
        raise PermissionError("bounded positive Stop Loss risk is required")
    return CandidateTrade(
        instrument=plan.construction.instrument,
        direction=plan.construction.direction,
        market_category=plan.construction.asset_class.value,
        requested_size=size,
        entry_price=plan.construction.entry,
        stop_loss=plan.construction.stop_loss,
        risk_per_unit=risk_per_unit,
        size_increment=Decimal(str(specification.get("quantity_step", "0.01"))),
        asset_class=plan.construction.asset_class,
        instrument_type=plan.construction.instrument_type,
        venue_instrument_id=plan.construction.venue_instrument_id,
        futures_contract_id=plan.construction.futures_contract_id,
        specification_version_id=plan.construction.specification_version_id,
        quantity_unit=plan.construction.quantity_unit,
        contract_multiplier=Decimal(str(specification.get("contract_multiplier", "1"))),
        tick_size=Decimal(str(specification.get("tick_size", "0.00001"))),
        tick_value=(
            Decimal(str(specification["tick_value"]))
            if specification.get("tick_value") is not None
            else None
        ),
        margin_required=Decimal(str(specification.get("margin_required", "0"))),
        financing_cost=Decimal(str(specification.get("financing_cost", "0"))),
    )


async def persist_trade_plan(
    session: AsyncSession, plan: TradePlan, *, actor_id: UUID | None = None
) -> ResourceRecord:
    """Persist a deterministic plan; blocked plans stop here with no command."""
    store = ResourceStore(session)
    existing = await store.get("trade_plan", plan.id, plan.owner_id)
    if existing is not None:
        return existing
    return await store.create(
        "trade_plan",
        plan.owner_id,
        plan.model_dump(mode="json"),
        state=plan.state.value,
        record_id=plan.id,
        actor_id=actor_id,
        event_type=(
            "trade_plan.blocked" if plan.state is TradePlanState.BLOCKED else "trade_plan.created"
        ),
    )


async def authorize_and_queue_entry(
    session: AsyncSession,
    plan: TradePlan,
    *,
    actor_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> tuple[ResourceRecord, ResourceRecord | None]:
    """Revalidate, reserve, authorize, and queue one entry in one DB transaction."""
    store = ResourceStore(session)
    plan_record = await persist_trade_plan(session, plan, actor_id=actor_id)
    if plan.state is TradePlanState.BLOCKED or plan.risk.decision is RiskDecision.HARD_BLOCK:
        return plan_record, None
    await current_broker_snapshot(session, plan.owner_id, plan.account_id)
    candidate = await _typed_candidate(session, plan)
    context = await authoritative_risk_context(
        session, plan.owner_id, plan.account_id, candidate
    )
    risk = RiskEngine().evaluate(context, candidate)
    if risk.decision is RiskDecision.HARD_BLOCK:
        blocked = plan.model_copy(update={"state": TradePlanState.BLOCKED, "risk": risk})
        plan_record = await store.update(
            plan_record,
            blocked.model_dump(mode="json"),
            state=TradePlanState.BLOCKED.value,
            actor_id=actor_id,
            event_type="trade_plan.blocked",
            evidence={"reasons": risk.reasons},
        )
        return plan_record, None
    plan = plan.model_copy(
        update={
            "risk": risk,
            "construction": plan.construction.model_copy(
                update={"approved_size": risk.approved_size}
            ),
        }
    )
    reservation = await PersistentReservationStore(session).reserve(
        owner_id=plan.owner_id,
        account_id=plan.account_id,
        trade_plan_id=plan.id,
        amount=risk.snapshot.candidate_trade_risk,
        available=risk.snapshot.remaining_portfolio_risk_capacity,
        details={
            "risk_snapshot": risk.snapshot.model_dump(mode="json"),
            "specification_version_id": str(plan.construction.specification_version_id),
        },
    )
    plan.reservation_id = reservation.id
    permissions = await current_permissions(session, plan.owner_id, plan.account_id, lock=True)
    platform_kill, account_kill = await current_kill_switches(
        session, plan.owner_id, plan.account_id, lock=True
    )
    service = ExecutionService()
    authorization = service.authorize(plan, permissions, platform_kill, account_kill)
    command = service.create_command(
        plan,
        authorization,
        idempotency_key=idempotency_key or f"entry:{plan.id}",
    )
    command = transition(transition(command, CommandState.AUTHORIZED), CommandState.QUEUED)
    await PersistentReservationStore(session).transition(
        reservation.id,
        owner_id=plan.owner_id,
        target=ReservationState.COMMAND_PENDING,
        command_id=command.id,
    )
    plan = transition_trade_plan(plan, TradePlanState.EXECUTION_PENDING)
    plan.execution_command_id = command.id
    plan_record = await store.update(
        plan_record,
        plan.model_dump(mode="json"),
        state=plan.state.value,
        actor_id=actor_id,
        event_type="trade_plan.execution_queued",
    )
    command_record = await persist_command(
        store, owner_id=plan.owner_id, command=command, actor_id=actor_id
    )
    return plan_record, command_record


async def authorize_and_queue_management(
    session: AsyncSession,
    *,
    owner_id: UUID,
    plan: TradePlan,
    action: ExecutionAction,
    postcondition: dict,
    idempotency_key: str,
    management_action_id: UUID,
    target_order_id: str | None = None,
    target_position_id: str | None = None,
    expected_broker_version: str | None = None,
) -> ResourceRecord:
    await current_broker_snapshot(session, owner_id, plan.account_id)
    permissions = await current_permissions(session, owner_id, plan.account_id, lock=True)
    platform_kill, account_kill = await current_kill_switches(
        session, owner_id, plan.account_id, lock=True
    )
    service = ExecutionService()
    authorization = service.authorize_action(
        plan, action, permissions, platform_kill, account_kill
    )
    plan_record = await ResourceStore(session).get("trade_plan", plan.id, owner_id)
    if plan_record is None:
        raise LookupError("management action Trade Plan is not persisted")
    plan.version += 1
    await ResourceStore(session).update(
        plan_record,
        plan.model_dump(mode="json"),
        state=plan.state.value,
        event_type="trade_plan.management_authorized",
        evidence={"action": action.value, "authorization_id": str(authorization.id)},
    )
    command = service.create_action_command(
        plan,
        authorization,
        idempotency_key=idempotency_key,
        requested_postcondition=postcondition,
        management_action_id=management_action_id,
        target_order_id=target_order_id,
        target_position_id=target_position_id,
        expected_broker_version=expected_broker_version,
    )
    command = transition(transition(command, CommandState.AUTHORIZED), CommandState.QUEUED)
    return await persist_command(
        ResourceStore(session), owner_id=owner_id, command=command
    )


__all__ = [
    "authorize_and_queue_entry",
    "authorize_and_queue_management",
    "current_broker_snapshot",
    "current_kill_switches",
    "current_permissions",
    "persist_trade_plan",
]
