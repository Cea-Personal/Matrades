from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.paper.model import PaperRun, PaperRunState
from traderx.shared.events import append_outbox, event_envelope
from traderx.shared.types import ConcurrentModification, InvalidTransition, utc_now
from traderx.strategies.approval_model import ApprovalDecision, StrategyApproval
from traderx.strategies.model import StrategyLifecycle, StrategyVersion


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    decision: ApprovalDecision
    evidence_current: bool
    mfa_at: datetime | None
    now: datetime


def approve(actor: Actor, command: ApprovalCommand) -> ApprovalDecision:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "strategy.approve", require_mfa=True)
    if command.decision == ApprovalDecision.APPROVE_LIVE:
        if not command.evidence_current:
            raise InvalidTransition("strategy approval needs current evidence")
        if command.mfa_at is None or command.now - command.mfa_at > timedelta(minutes=5):
            raise InvalidTransition("strategy approval needs recent MFA")
    return command.decision


def record_approval(
    database: Session,
    actor: Actor,
    *,
    strategy_version_id: UUID,
    paper_run_id: UUID,
    decision: ApprovalDecision,
    reason: str,
    expected_etag: str,
    mfa_at: datetime | None,
    idempotency_key: str,
    correlation_id: str,
) -> StrategyApproval:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "strategy.approve", require_mfa=True)
    version = database.get(StrategyVersion, strategy_version_id)
    run = database.get(PaperRun, paper_run_id)
    if version is None or run is None or run.strategy_version_id != strategy_version_id:
        raise InvalidTransition("approval requires paper evidence for this exact strategy version")
    actual_etag = f'"strategy-version-{version.id}-{version.version}"'
    if expected_etag != actual_etag:
        raise ConcurrentModification("strategy approval evidence changed; refresh before deciding")
    now = utc_now()
    evidence_current = bool(
        run.finished_at
        and now - _aware(run.finished_at) <= timedelta(hours=24)
        and run.state == PaperRunState.AWAITING_APPROVAL
    )
    approve(
        actor,
        ApprovalCommand(
            decision=decision,
            evidence_current=evidence_current,
            mfa_at=_aware(mfa_at) if mfa_at else None,
            now=now,
        ),
    )
    existing = database.scalar(
        select(StrategyApproval)
        .join(AuditEvent, AuditEvent.target_id == StrategyApproval.id)
        .where(AuditEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    approval = StrategyApproval(
        strategy_version_id=version.id,
        paper_run_id=run.id,
        decision=decision,
        actor_id=actor.id,
        assurance_snapshot={
            "assurance": actor.assurance,
            "mfa_at": mfa_at.isoformat() if mfa_at else None,
        },
        evidence_hash=run.evidence_hash,
        reason=reason.strip(),
        decided_at=now,
    )
    database.add(approval)
    database.flush()
    previous = version.lifecycle
    if decision == ApprovalDecision.APPROVE_LIVE:
        if version.lifecycle != StrategyLifecycle.AWAITING_APPROVAL:
            raise InvalidTransition("only a strategy awaiting approval can become live approved")
        version.lifecycle = StrategyLifecycle.LIVE_APPROVED
    elif decision == ApprovalDecision.REJECT:
        version.lifecycle = StrategyLifecycle.REJECTED
    else:
        version.lifecycle = StrategyLifecycle.RESEARCH
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role,
            action="strategy.approval.decide",
            outcome="SUCCEEDED",
            target_type="strategy_approval",
            target_id=approval.id,
            target_version=approval.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value={"lifecycle": previous},
            new_value={"lifecycle": version.lifecycle, "decision": decision},
            occurred_at=now,
        )
    )
    append_outbox(
        database,
        aggregate_type="strategy_version",
        aggregate_id=version.id,
        aggregate_version=version.version,
        event_type="traderx.strategy.approval.decided.v1",
        envelope=event_envelope(
            source="/traderx/strategies",
            event_type="traderx.strategy.approval.decided.v1",
            subject=str(version.id),
            data={"decision": decision, "paper_run_id": str(run.id), "reason": reason},
            now=now,
            correlation_id=correlation_id,
            actor_id=actor.id,
            aggregate_version=version.version,
        ),
    )
    database.flush()
    return approval


def approval_payload(approval: StrategyApproval) -> dict[str, object]:
    return {
        "id": str(approval.id),
        "strategy_version_id": str(approval.strategy_version_id),
        "paper_run_id": str(approval.paper_run_id),
        "decision": approval.decision,
        "evidence_hash": approval.evidence_hash,
        "reason": approval.reason,
        "decided_at": _aware(approval.decided_at).isoformat(),
    }


def _aware(value: datetime) -> datetime:
    from datetime import UTC

    return value if value.tzinfo else value.replace(tzinfo=UTC)
