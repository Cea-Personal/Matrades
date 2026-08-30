"""Deterministic command authorization and idempotent dispatch primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from modules.risk.models import RiskDecision
from modules.trading.models import (
    CommandState,
    ExecutionAction,
    ExecutionAttempt,
    ExecutionAuthorization,
    ExecutionCommand,
    ExecutionPermissionProfile,
    KillSwitchState,
    OutcomeCertainty,
    TradePlan,
    TradePlanState,
)
from packages.shared.domain_types import utc_now


class BrokerCommandPort(Protocol):
    async def submit_order(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict[str, Any]: ...

    async def cancel_order(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict[str, Any]: ...

    async def change_protection(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict[str, Any]: ...

    async def partial_close(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict[str, Any]: ...

    async def full_exit(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict[str, Any]: ...


class CommandConflict(ValueError):
    """The same idempotency key was reused for a different economic intent."""


class CommandTransitionError(ValueError):
    """A command attempted an unsafe or out-of-order lifecycle transition."""


_TRANSITIONS: dict[CommandState, set[CommandState]] = {
    CommandState.CREATED: {CommandState.VALIDATING, CommandState.AUTHORIZED, CommandState.BLOCKED},
    CommandState.VALIDATING: {CommandState.AUTHORIZED, CommandState.BLOCKED},
    CommandState.AUTHORIZED: {CommandState.QUEUED, CommandState.EXPIRED, CommandState.BLOCKED},
    CommandState.QUEUED: {CommandState.DISPATCHING, CommandState.EXPIRED},
    CommandState.DISPATCHING: {
        CommandState.ACKNOWLEDGED,
        CommandState.REJECTED,
        CommandState.OUTCOME_UNKNOWN,
        CommandState.RECONCILING,
    },
    CommandState.RECONCILING: {
        CommandState.ACKNOWLEDGED,
        CommandState.APPLIED,
        CommandState.NO_EFFECT_CONFIRMED,
        CommandState.BLOCKED_AMBIGUOUS,
    },
    CommandState.ACKNOWLEDGED: {
        CommandState.PARTIALLY_APPLIED,
        CommandState.APPLIED,
        CommandState.RECONCILING,
        CommandState.REJECTED,
    },
    CommandState.PARTIALLY_APPLIED: {
        CommandState.APPLIED,
        CommandState.RECONCILING,
    },
    CommandState.OUTCOME_UNKNOWN: {CommandState.RECONCILING},
}


def transition(command: ExecutionCommand, target: CommandState) -> ExecutionCommand:
    if target is command.state:
        return command
    if target not in _TRANSITIONS.get(command.state, set()):
        raise CommandTransitionError(f"cannot transition {command.state} to {target}")
    return command.model_copy(update={"state": target, "version": command.version + 1})


class ExecutionLedger:
    """A durable-boundary-compatible ledger used by the service and recording adapter.

    Production callers persist these models in PostgreSQL in the same transaction as the outbox
    insert. Keeping identity checks here prevents duplicate economic intents on worker retry.
    """

    def __init__(self) -> None:
        self.commands: dict[UUID, ExecutionCommand] = {}
        self.by_idempotency: dict[str, UUID] = {}
        self.outbox: list[dict[str, Any]] = []

    def put(self, command: ExecutionCommand) -> ExecutionCommand:
        existing_id = self.by_idempotency.get(command.idempotency_key)
        if existing_id is not None:
            existing = self.commands[existing_id]
            if existing.requested_postcondition != command.requested_postcondition:
                raise CommandConflict("idempotency key is bound to a different command payload")
            return existing
        self.by_idempotency[command.idempotency_key] = command.id
        self.commands[command.id] = command
        self.outbox.append(
            {
                "event_type": "execution.command.created",
                "command_id": str(command.id),
                "account_id": str(command.account_id),
                "idempotency_key": command.idempotency_key,
            }
        )
        return command


class ExecutionService:
    def __init__(self, ledger: ExecutionLedger | None = None) -> None:
        self.ledger = ledger or ExecutionLedger()

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def authorize(
        self,
        plan: TradePlan,
        permissions: ExecutionPermissionProfile,
        platform_kill: KillSwitchState,
        account_kill: KillSwitchState,
        *,
        ttl_seconds: int = 60,
    ) -> ExecutionAuthorization:
        return self.authorize_action(
            plan,
            ExecutionAction.PLACE_ORDER,
            permissions,
            platform_kill,
            account_kill,
            ttl_seconds=ttl_seconds,
        )

    def authorize_action(
        self,
        plan: TradePlan,
        action: ExecutionAction,
        permissions: ExecutionPermissionProfile,
        platform_kill: KillSwitchState,
        account_kill: KillSwitchState,
        *,
        ttl_seconds: int = 60,
    ) -> ExecutionAuthorization:
        now = utc_now()
        allowed_states = (
            {TradePlanState.READY, TradePlanState.AUTHORIZED}
            if action is ExecutionAction.PLACE_ORDER
            else {
                TradePlanState.ACTIVE,
                TradePlanState.AUTHORIZED,
                TradePlanState.EXECUTION_PENDING,
            }
        )
        if plan.state not in allowed_states:
            raise ValueError("trade plan is not eligible for the requested action")
        if action is ExecutionAction.PLACE_ORDER and plan.expires_at <= now:
            raise ValueError("trade plan has expired")
        if plan.risk.decision == RiskDecision.HARD_BLOCK:
            raise ValueError("hard-blocked trade plans cannot be authorized")
        if not permissions.allows(action):
            raise PermissionError(f"{action.value} permission is disabled")
        if platform_kill.active or account_kill.active:
            raise PermissionError("platform or account kill switch is active")
        digest = self._digest(
            {
                "plan": str(plan.id),
                "account": str(plan.account_id),
                "permission": permissions.version,
                "platform_epoch": platform_kill.safety_epoch,
                "account_epoch": account_kill.safety_epoch,
                "action": action.value,
                "risk": plan.risk.model_dump(mode="json"),
            }
        )
        authorization = ExecutionAuthorization(
            account_id=plan.account_id,
            action=action,
            permission_version=permissions.version,
            platform_safety_epoch=platform_kill.safety_epoch,
            account_safety_epoch=account_kill.safety_epoch,
            authorization_digest=digest,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        plan.authorization = authorization
        if action is ExecutionAction.PLACE_ORDER:
            plan.state = TradePlanState.AUTHORIZED
        return authorization

    def create_command(
        self,
        plan: TradePlan,
        authorization: ExecutionAuthorization,
        *,
        idempotency_key: str,
    ) -> ExecutionCommand:
        if authorization.account_id != plan.account_id:
            raise ValueError("authorization account does not match trade plan")
        if authorization.expires_at <= utc_now():
            raise ValueError("execution authorization has expired")
        command = ExecutionCommand(
            account_id=plan.account_id,
            action=authorization.action,
            trade_plan_id=plan.id,
            authorization_id=authorization.id,
            idempotency_key=idempotency_key,
            requested_postcondition={
                "instrument": plan.construction.instrument,
                "direction": plan.construction.direction.value,
                "quantity": str(plan.construction.approved_size),
                "quantity_unit": plan.construction.quantity_unit.value,
                "entry": str(plan.construction.entry),
                "stop_loss": str(plan.construction.stop_loss),
                "targets": [str(target) for target in plan.construction.targets],
                "venue_instrument_id": str(plan.construction.venue_instrument_id),
                "specification_version_id": str(plan.construction.specification_version_id),
            },
        )
        return self.ledger.put(command)

    def create_action_command(
        self,
        plan: TradePlan,
        authorization: ExecutionAuthorization,
        *,
        idempotency_key: str,
        requested_postcondition: dict[str, Any],
        management_action_id: UUID | None = None,
        target_order_id: str | None = None,
        target_position_id: str | None = None,
        expected_broker_version: str | None = None,
    ) -> ExecutionCommand:
        if authorization.account_id != plan.account_id:
            raise ValueError("authorization account does not match trade plan")
        if authorization.expires_at <= utc_now():
            raise ValueError("execution authorization has expired")
        command = ExecutionCommand(
            account_id=plan.account_id,
            action=authorization.action,
            trade_plan_id=plan.id,
            management_action_id=management_action_id,
            authorization_id=authorization.id,
            idempotency_key=idempotency_key,
            requested_postcondition=requested_postcondition,
            target_order_id=target_order_id,
            target_position_id=target_position_id,
            expected_broker_version=expected_broker_version,
        )
        return self.ledger.put(command)

    @staticmethod
    def _adapter_call(
        command: ExecutionCommand,
        adapter: BrokerCommandPort,
    ) -> Callable[[ExecutionCommand, ExecutionAuthorization], Awaitable[dict[str, Any]]]:
        if command.action is ExecutionAction.PLACE_ORDER:
            return adapter.submit_order
        if command.action is ExecutionAction.CANCEL_ORDER:
            return adapter.cancel_order
        if command.action in {
            ExecutionAction.SET_OR_CHANGE_STOP_LOSS,
            ExecutionAction.SET_OR_CHANGE_TAKE_PROFIT,
        }:
            return adapter.change_protection
        if command.action is ExecutionAction.PARTIAL_CLOSE:
            return adapter.partial_close
        if command.action is ExecutionAction.FULL_EXIT:
            return adapter.full_exit
        raise ValueError(f"unsupported execution action: {command.action}")

    async def dispatch(
        self,
        command: ExecutionCommand,
        authorization: ExecutionAuthorization,
        adapter: BrokerCommandPort,
    ) -> ExecutionCommand:
        if command.state in {
            CommandState.APPLIED,
            CommandState.REJECTED,
            CommandState.BLOCKED_AMBIGUOUS,
        }:
            return command
        if command.state in {CommandState.OUTCOME_UNKNOWN, CommandState.RECONCILING}:
            raise CommandTransitionError("uncertain command must reconcile before retry")
        if command.state is CommandState.CREATED:
            command = transition(command, CommandState.AUTHORIZED)
        if command.state is CommandState.AUTHORIZED:
            command = transition(command, CommandState.QUEUED)
        if command.state is CommandState.QUEUED:
            command = transition(command, CommandState.DISPATCHING)
        elif command.state is not CommandState.DISPATCHING:
            raise CommandTransitionError(f"command {command.state} cannot dispatch")
        request_digest = self._digest(command.requested_postcondition)
        attempt = ExecutionAttempt(
            attempt=len(command.attempts) + 1,
            state=CommandState.DISPATCHING,
            request_digest=request_digest,
        )
        command.attempts.append(attempt)
        try:
            response = await self._adapter_call(command, adapter)(command, authorization)
        except Exception as exc:  # noqa: BLE001 - uncertain transport outcome is explicit
            attempt.state = CommandState.OUTCOME_UNKNOWN
            attempt.error_code = type(exc).__name__
            command = command.model_copy(
                update={
                    "state": CommandState.OUTCOME_UNKNOWN,
                    "version": command.version + 1,
                }
            )
            command.outcome_certainty = OutcomeCertainty.UNCERTAIN
            return command
        attempt.response_digest = self._digest(response)
        attempt.state = CommandState.ACKNOWLEDGED
        command = command.model_copy(
            update={"state": CommandState.ACKNOWLEDGED, "version": command.version + 1}
        )
        command.outcome_certainty = (
            OutcomeCertainty.CONFIRMED if response.get("confirmed") else OutcomeCertainty.UNCERTAIN
        )
        command.broker_order_id = (
            str(response.get("broker_order_id")) if response.get("broker_order_id") else None
        )
        if response.get("rejected"):
            command = command.model_copy(
                update={"state": CommandState.REJECTED, "version": command.version + 1}
            )
        return command
