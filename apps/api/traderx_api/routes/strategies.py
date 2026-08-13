from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/strategies", tags=["Strategies"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


class StrategyCommand(BaseModel):
    name: str = Field(min_length=1)
    definition: dict[str, object]


@router.get("")
def list_strategies() -> dict[str, object]:
    return {"items": []}


@router.post("", status_code=201)
def create_strategy(
    payload: StrategyCommand,
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "name": payload.name,
        "definition": payload.definition,
        "lifecycle": "DRAFT",
        "idempotency_key": idempotency_key,
    }


@router.get("/{strategy_id}/versions/{version}")
def strategy_version(strategy_id: str, version: int, response: Response) -> dict[str, object]:
    response.headers["ETag"] = f'"strategy-{strategy_id}-{version}"'
    return {"strategy_id": strategy_id, "version": version, "immutable": True, "lifecycle": "DRAFT"}
