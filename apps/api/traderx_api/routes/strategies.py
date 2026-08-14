from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.research.model import ResearchJobDetail
from traderx.research.service import ResearchRequest, create_research_job
from traderx.strategies.lifecycle import (
    create_immutable_version,
    create_strategy_with_version,
    strategy_payload,
    strategy_version_payload,
)
from traderx.strategies.model import Strategy, StrategyVersion
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
    dependencies=[Depends(authenticated_operation_context)],
)
research_router = APIRouter(
    prefix="/research-jobs",
    tags=["Research and Strategies"],
    dependencies=[Depends(authenticated_operation_context)],
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class StrategyDefinitionCommand(BaseModel):
    regime: str = Field(min_length=1, max_length=64)
    direction: Literal["LONG", "SHORT", "BOTH"] = "BOTH"
    timeframes: list[str] = Field(min_length=1)
    conditions: list[dict[str, object]] = Field(min_length=1)
    filters: list[dict[str, object]] = Field(default_factory=list)
    stop: dict[str, object]
    target: dict[str, object]
    invalidation: dict[str, object]
    expiration: dict[str, object]
    risk_fraction: Decimal = Field(gt=0, le=Decimal("0.02"))


class StrategyCommand(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    instrument_id: UUID
    definition: StrategyDefinitionCommand
    change_summary: str = Field(
        default="Initial deterministic draft", min_length=8, max_length=2000
    )


class StrategyVersionCommand(BaseModel):
    definition: StrategyDefinitionCommand
    change_summary: str = Field(min_length=8, max_length=2000)


class ResearchJobCommand(BaseModel):
    purpose: str = Field(min_length=3, max_length=128)
    inputs: dict[str, object] = Field(default_factory=dict)
    parameters: dict[str, object] = Field(default_factory=dict)


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(
        role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id
    )


@router.get("")
def list_strategies(database: DatabaseSession) -> dict[str, object]:
    strategies = database.scalars(select(Strategy).order_by(Strategy.created_at.desc())).all()
    return {"items": [strategy_payload(database, strategy) for strategy in strategies]}


@router.post("", status_code=201)
def create_strategy(
    payload: StrategyCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    strategy, version = create_strategy_with_version(
        database,
        _actor(context),
        name=payload.name,
        instrument_id=payload.instrument_id,
        definition_payload=payload.definition.model_dump(mode="json"),
        change_summary=payload.change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    database.refresh(strategy)
    response.headers["ETag"] = f'"strategy-{strategy.id}-{strategy.version}"'
    return {
        **strategy_payload(database, strategy),
        "created_version": strategy_version_payload(version),
    }


@router.post("/{strategy_id}/versions", status_code=201)
def create_strategy_version(
    strategy_id: UUID,
    payload: StrategyVersionCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    version = create_immutable_version(
        database,
        _actor(context),
        strategy_id=strategy_id,
        expected_etag=if_match,
        definition_payload=payload.definition.model_dump(mode="json"),
        change_summary=payload.change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    database.refresh(version)
    response.headers["ETag"] = f'"strategy-version-{version.id}-{version.version}"'
    return strategy_version_payload(version)


@router.get("/{strategy_id}/versions/{sequence}")
def strategy_version(
    strategy_id: UUID,
    sequence: int,
    response: Response,
    database: DatabaseSession,
) -> dict[str, object]:
    version = database.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.sequence == sequence,
        )
    )
    if version is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the requested immutable strategy version does not exist")
    response.headers["ETag"] = f'"strategy-version-{version.id}-{version.version}"'
    return strategy_version_payload(version)


@router.get("/{strategy_id}/versions")
def strategy_versions(strategy_id: UUID, database: DatabaseSession) -> dict[str, object]:
    versions = database.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.sequence.desc())
    ).all()
    return {"items": [strategy_version_payload(version) for version in versions]}


@research_router.post("", status_code=202)
def start_strategy_research(
    payload: ResearchJobCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    job, detail = create_research_job(
        database,
        owner_id=context.user.id,
        request=ResearchRequest(payload.purpose, payload.inputs, payload.parameters),
    )
    database.commit()
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    response.headers["Idempotency-Key"] = idempotency_key
    return {
        "job": {"id": str(job.id), "state": job.state},
        "research_detail_id": str(detail.id),
        "manifest_hash": job.input_manifest["hash"],
    }


@research_router.get("/{job_id}")
def research_job(job_id: UUID, database: DatabaseSession) -> dict[str, object]:
    detail = database.scalar(select(ResearchJobDetail).where(ResearchJobDetail.job_id == job_id))
    if detail is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the requested research job does not exist")
    return {
        "id": str(detail.id),
        "job_id": str(detail.job_id),
        "purpose": detail.purpose,
        "input_manifest": detail.input_manifest,
        "result_summary": detail.result_summary,
        "created_at": detail.created_at.isoformat(),
    }
