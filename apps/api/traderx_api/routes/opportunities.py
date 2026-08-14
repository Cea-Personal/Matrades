from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.opportunities.evaluator import (
    evaluate_current_opportunities,
    opportunity_payload,
    recommendation_payload,
)
from traderx.opportunities.model import Opportunity
from traderx.shared.types import InvalidTransition
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/opportunities",
    tags=["Opportunities"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("")
def opportunities(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    items = database.scalars(select(Opportunity).order_by(Opportunity.created_at.desc())).all()
    return {
        "items": [opportunity_payload(database, item) for item in items],
        "risk_authorization_is_separate": True,
        "no_execution_capability": True,
    }


@router.post("/evaluate", status_code=202)
def evaluate(
    _: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    items = evaluate_current_opportunities(database)
    database.commit()
    return {
        "items": [opportunity_payload(database, item) for item in items],
        "idempotency_key": idempotency_key,
        "no_execution_capability": True,
    }


@router.get("/{opportunity_id}/recommendation")
def recommendation(opportunity_id: UUID, _: Viewer, database: DatabaseSession) -> dict[str, object]:
    opportunity = database.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise InvalidTransition("the requested opportunity does not exist")
    payload = recommendation_payload(database, opportunity)
    database.commit()
    return payload
