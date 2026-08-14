from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.integrations.crypto import redact
from traderx.integrations.health import aggregate_health, operational_components
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.jobs.model import BackgroundJob, JobState
from traderx.risk.model import CircuitBreaker, CircuitBreakerState, RiskSnapshot
from traderx.shared.types import utc_now
from traderx.strategies.health_model import StrategyHealthObservation
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/operations",
    tags=["Operations"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("/health")
def health(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    integrations = database.scalars(select(Integration).where(Integration.state != "REMOVED")).all()
    components: dict[str, str] = {"database": "HEALTHY", "api": "HEALTHY"}
    for integration in integrations:
        components[f"integration:{integration.name}"] = (
            "HEALTHY" if integration.state == "HEALTHY" else "DEGRADED"
        )
    failed_jobs = (
        database.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(BackgroundJob.state == JobState.FAILED)
        )
        or 0
    )
    stalled_before = utc_now() - timedelta(minutes=5)
    stalled_jobs = (
        database.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(
                BackgroundJob.state == JobState.RUNNING,
                BackgroundJob.started_at < stalled_before,
            )
        )
        or 0
    )
    queued_jobs = (
        database.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(BackgroundJob.state == JobState.QUEUED)
        )
        or 0
    )
    latest_risk = database.scalar(
        select(RiskSnapshot).order_by(RiskSnapshot.calculated_at.desc()).limit(1)
    )
    risk_age = (
        (utc_now() - _aware(latest_risk.calculated_at)).total_seconds() if latest_risk else None
    )
    components = operational_components(
        base=components,
        failed_jobs=failed_jobs,
        stalled_jobs=stalled_jobs,
        queued_jobs=queued_jobs,
        account_data_verified=bool(latest_risk and latest_risk.quality == "VERIFIED"),
        account_age_seconds=risk_age,
    )
    result = aggregate_health(components)
    breakers = database.scalars(
        select(CircuitBreaker).where(CircuitBreaker.state == CircuitBreakerState.TRIPPED)
    ).all()
    observations = database.scalars(
        select(IntegrationHealthObservation)
        .order_by(IntegrationHealthObservation.observed_at.desc())
        .limit(20)
    ).all()
    strategy_health = database.scalars(
        select(StrategyHealthObservation)
        .order_by(StrategyHealthObservation.observed_at.desc())
        .limit(20)
    ).all()
    return {
        "status": result.status,
        "components": result.components,
        "safety_impact": list(result.safety_impact),
        "circuit_breakers": [
            {
                "id": str(item.id),
                "type": item.breaker_type,
                "scope": item.scope,
                "state": item.state,
                "reason": item.reason,
                "tripped_at": item.tripped_at.isoformat() if item.tripped_at else None,
            }
            for item in breakers
        ],
        "integration_observations": [
            {
                "id": str(item.id),
                "integration_id": str(item.integration_id),
                "status": item.status,
                "evidence": redact(item.evidence),
                "observed_at": item.observed_at.isoformat(),
            }
            for item in observations
        ],
        "strategy_health": [
            {
                "id": str(item.id),
                "strategy_version_id": str(item.strategy_version_id),
                "state": item.state,
                "evidence": item.evidence,
                "observed_at": item.observed_at.isoformat(),
            }
            for item in strategy_health
        ],
        "secrets_redacted": True,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@router.get("/audit")
def audit(
    _: Viewer,
    database: DatabaseSession,
    action: str | None = None,
    outcome: str | None = None,
    target_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    query = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    if action:
        query = query.where(AuditEvent.action == action)
    if outcome:
        query = query.where(AuditEvent.outcome == outcome)
    if target_id:
        query = query.where(AuditEvent.target_id == target_id)
    items = database.scalars(query).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "actor_type": item.actor_type,
                "actor_id": str(item.actor_id) if item.actor_id else None,
                "actor_role": item.actor_role,
                "action": item.action,
                "outcome": item.outcome,
                "target_type": item.target_type,
                "target_id": str(item.target_id) if item.target_id else None,
                "target_version": item.target_version,
                "reason": item.reason,
                "assurance": item.assurance,
                "correlation_id": item.correlation_id,
                "previous_value": redact(item.previous_value),
                "new_value": redact(item.new_value),
                "occurred_at": item.occurred_at.isoformat(),
                "integrity_hash": item.integrity_hash,
            }
            for item in items
        ],
        "append_only": True,
        "redacted": True,
    }
