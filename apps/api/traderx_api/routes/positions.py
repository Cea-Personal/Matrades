from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.audit.model import AuditEvent
from traderx.integrations.broker_service import sync_selected_broker_account
from traderx.integrations.model import Integration
from traderx.monitoring.position_model import Position, PositionClassification
from traderx.monitoring.reconciliation import position_payload, thesis_payload
from traderx.monitoring.thesis_model import TradeThesis
from traderx.opportunities.recommendation_model import Recommendation
from traderx.shared.types import ConcurrentModification, InvalidTransition, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/positions",
    tags=["Trade Monitoring"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class ClassificationCommand(BaseModel):
    classification: Literal["RECOMMENDED", "DISCRETIONARY", "UNRESOLVED"]
    reason: str = Field(min_length=8, max_length=2000)
    recommendation_id: UUID | None = None


@router.get("")
def positions(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    items = database.scalars(select(Position).order_by(Position.opened_at.desc())).all()
    return {
        "items": [position_payload(database, item) for item in items],
        "broker_mode": "READ_ONLY",
        "no_execution_capability": True,
    }


@router.post("/refresh", status_code=202)
def refresh_positions(_: Operator, database: DatabaseSession) -> dict[str, object]:
    accounts = database.scalars(
        select(TradingAccount).where(TradingAccount.broker_integration_id.is_not(None))
    ).all()
    refreshed = 0
    for account in accounts:
        integration = database.get(Integration, account.broker_integration_id)
        if integration is None:
            continue
        try:
            sync_selected_broker_account(database, integration, account)
            refreshed += 1
        except InvalidTransition:
            database.commit()
            raise
    database.commit()
    return {"status": "COMPLETED", "accounts_refreshed": refreshed, "broker_mode": "READ_ONLY"}


@router.put("/{position_id}/classification")
def correct_classification(
    position_id: UUID,
    payload: ClassificationCommand,
    context: Operator,
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    position = database.get(Position, position_id)
    if position is None:
        raise InvalidTransition("the requested position does not exist")
    if if_match != f'"position-{position.id}-{position.version}"':
        raise ConcurrentModification("the position changed; refresh before correcting it")
    recommendation = (
        database.get(Recommendation, payload.recommendation_id)
        if payload.recommendation_id
        else None
    )
    if payload.classification == PositionClassification.RECOMMENDED and recommendation is None:
        raise InvalidTransition("recommended classification requires a valid recommendation")
    previous = {
        "classification": position.classification,
        "recommendation_id": str(position.matched_recommendation_id)
        if position.matched_recommendation_id
        else None,
    }
    position.classification = payload.classification
    position.matched_recommendation_id = recommendation.id if recommendation else None
    position.match_confidence = 1 if recommendation else 0
    position.classification_reason = "USER_CORRECTION"
    now = utc_now()
    if (
        recommendation is not None
        and database.scalar(select(TradeThesis).where(TradeThesis.position_id == position.id))
        is None
    ):
        database.add(
            TradeThesis(
                position_id=position.id,
                recommendation_id=recommendation.id,
                frozen_evidence={
                    "entry": str(recommendation.entry),
                    "stop": str(recommendation.stop),
                    "targets": recommendation.targets,
                    "invalidation": recommendation.invalidation,
                    "reason_trace": recommendation.reason_trace,
                },
                created_at=now,
            )
        )
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=context.user.id,
            actor_role=context.user.role,
            action="position.classification.correct",
            outcome="SUCCEEDED",
            target_type="position",
            target_id=position.id,
            target_version=position.version,
            reason=payload.reason,
            assurance=context.session.assurance,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous,
            new_value={
                "classification": position.classification,
                "recommendation_id": str(position.matched_recommendation_id)
                if position.matched_recommendation_id
                else None,
            },
            occurred_at=now,
        )
    )
    database.commit()
    database.refresh(position)
    return {**position_payload(database, position), "audited": True}


@router.get("/{position_id}/thesis")
def position_thesis(position_id: UUID, _: Viewer, database: DatabaseSession) -> dict[str, object]:
    position = database.get(Position, position_id)
    if position is None:
        raise InvalidTransition("the requested position does not exist")
    return thesis_payload(database, position)
