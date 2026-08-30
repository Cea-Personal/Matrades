"""Typed asset-class × instrument-type research matrix endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.research import run_research_cycle
from modules.connections.models import (
    MarketDataCapability,
    ProviderAuthorityPurpose,
)
from modules.identity.authorization import Actor, Role
from modules.research.matrix import ALL_LANES, normalize_matrix
from packages.shared.domain_types import AssetClass, InstrumentType, ResearchLaneKey
from packages.shared.store import ResourceStore

router = APIRouter(tags=["Research"])


class MatrixLaneInput(ResearchLaneKey):
    enabled: bool = True


class ResearchMatrixInput(BaseModel):
    lanes: list[MatrixLaneInput] = Field(min_length=1, max_length=12)
    schedule: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_lanes(self) -> ResearchMatrixInput:
        keys = [lane.as_string() for lane in self.lanes]
        if len(keys) != len(set(keys)):
            raise ValueError("research matrix lanes must be unique")
        return self


class ResearchRunInput(BaseModel):
    account_id: UUID
    lanes: list[ResearchLaneKey] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def unique_requested_lanes(self) -> ResearchRunInput:
        if self.lanes is not None:
            keys = [lane.as_string() for lane in self.lanes]
            if len(keys) != len(set(keys)):
                raise ValueError("requested lanes must be unique")
        return self


class ProviderBindingRouteInput(BaseModel):
    """An account-scoped provider authority for a market lane or economic context."""

    binding_scope: Literal["MARKET_RESEARCH", "ECONOMIC_CONTEXT"] = "MARKET_RESEARCH"
    lane: ResearchLaneKey | None = None
    capability: str
    authority_purpose: str
    connection_id: UUID
    priority: int = Field(default=1, ge=1)
    provider_venue: str | None = None
    freshness_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def scope_has_required_lane(self) -> ProviderBindingRouteInput:
        if self.binding_scope == "MARKET_RESEARCH":
            if self.lane is None:
                raise ValueError("a market-research provider binding requires a matrix lane")
            try:
                MarketDataCapability(self.capability)
                ProviderAuthorityPurpose(self.authority_purpose)
            except ValueError as exc:
                raise ValueError(
                    "unsupported market provider capability or authority purpose"
                ) from exc
        elif self.lane is not None:
            raise ValueError("economic-context provider bindings do not use a market lane")
        return self


def _matrix_data(account_id: UUID, payload: ResearchMatrixInput, version: int) -> dict[str, Any]:
    normalized = normalize_matrix(
        account_id,
        [ResearchLaneKey.model_validate(item.model_dump()) for item in payload.lanes],
        version=version,
        schedule=payload.schedule,
    )
    normalized["lanes"] = [item.model_dump(mode="json") for item in payload.lanes]
    normalized["effective_from"] = datetime.now(UTC).isoformat()
    return normalized


async def _account(store: ResourceStore, actor: Actor, account_id: UUID):
    record = await store.get("account", account_id, actor.owner_id)
    if record is None or record.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return record


@router.get("/accounts/{account_id}/research-matrix")
async def get_account_research_matrix(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    record = next(
        (
            item
            for item in await store.list("research_matrix", actor.owner_id)
            if item.data.get("account_id") == str(account_id)
        ),
        None,
    )
    if record is None:
        return {
            "id": None,
            "account_id": str(account_id),
            "version": 1,
            "lanes": [{**lane.model_dump(mode="json"), "enabled": True} for lane in ALL_LANES],
            "schedule": {"enabled": False, "run_at": "00:00", "timezone": "UTC", "weekdays": []},
            "effective_from": None,
        }
    return record.public()


@router.get("/accounts/{account_id}/research-matrix/versions")
async def list_account_research_matrix_versions(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    records = [
        item.public()
        for item in await store.list("research_matrix", actor.owner_id)
        if item.data.get("account_id") == str(account_id)
    ]
    return sorted(records, key=lambda item: int(item.get("version", 0)), reverse=True)


@router.post("/accounts/{account_id}/research-matrix/versions/{matrix_id}/restore")
async def restore_account_research_matrix_version(
    account_id: UUID,
    matrix_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Restore an immutable historical matrix by creating a new active version."""
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    source = await store.get("research_matrix", matrix_id, actor.owner_id)
    if source is None or source.data.get("account_id") != str(account_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "research matrix version not found")
    history = [
        item
        for item in await store.list("research_matrix", actor.owner_id)
        if item.data.get("account_id") == str(account_id)
    ]
    version = max((int(item.data.get("version", 0)) for item in history), default=0) + 1
    restored = {
        **source.data,
        "account_id": str(account_id),
        "version": version,
        "restored_from_matrix_id": str(source.id),
        "restored_from_version": source.data.get("version"),
        "effective_from": datetime.now(UTC).isoformat(),
    }
    record = await store.create(
        "research_matrix",
        actor.owner_id,
        restored,
        actor_id=actor.actor_id,
        event_type="research_matrix.restored",
    )
    return record.public()


@router.put("/accounts/{account_id}/research-matrix")
async def replace_account_research_matrix(
    account_id: UUID,
    payload: ResearchMatrixInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    previous = [
        item
        for item in await store.list("research_matrix", actor.owner_id)
        if item.data.get("account_id") == str(account_id)
    ]
    version = max((int(item.data.get("version", 0)) for item in previous), default=0) + 1
    data = _matrix_data(account_id, payload, version)
    record = await store.create(
        "research_matrix",
        actor.owner_id,
        data,
        actor_id=actor.actor_id,
        event_type="research_matrix.activated",
    )
    return record.public()


@router.get("/accounts/{account_id}/provider-bindings")
async def list_account_provider_bindings(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    records = await store.list("provider_binding", actor.owner_id)
    return [item.public() for item in records if item.data.get("account_id") == str(account_id)]


@router.post("/accounts/{account_id}/provider-bindings", status_code=status.HTTP_201_CREATED)
async def create_account_provider_binding(
    account_id: UUID,
    payload: ProviderBindingRouteInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    connection = await store.get("connection", payload.connection_id, actor.owner_id)
    if connection is None or connection.state == "DELETED":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "connection not found")
    if payload.binding_scope == "MARKET_RESEARCH":
        active_matrix = next(
            (
                item
                for item in await store.list("research_matrix", actor.owner_id)
                if item.data.get("account_id") == str(account_id)
            ),
            None,
        )
        active_lanes = (
            active_matrix.data.get("lanes", [])
            if active_matrix
            else [lane.model_dump(mode="json") for lane in ALL_LANES]
        )
        enabled_lanes = {
            f"{item['asset_class']}:{item['instrument_type']}"
            for item in active_lanes
            if isinstance(item, dict) and item.get("enabled", True)
        }
        lane_key = payload.lane.as_string() if payload.lane else ""
        if lane_key not in enabled_lanes:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "the selected lane is not enabled in this account's active research matrix",
            )
    binding_data = {
        **payload.model_dump(mode="json"),
        "account_id": str(account_id),
        "verification_status": "UNVERIFIED",
    }
    record = await store.create(
        "provider_binding",
        actor.owner_id,
        binding_data,
        record_id=uuid4(),
        actor_id=actor.actor_id,
        event_type="provider_binding.created",
    )
    return record.public()


@router.post("/accounts/{account_id}/provider-bindings/{binding_id}/verify")
async def verify_account_provider_binding(
    account_id: UUID,
    binding_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, account_id)
    record = await store.get("provider_binding", binding_id, actor.owner_id)
    if record is None or record.data.get("account_id") != str(account_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider binding not found")
    connection = await store.get(
        "connection", UUID(str(record.data["connection_id"])), actor.owner_id
    )
    health = connection.data.get("health") if connection is not None else None
    health = health or (connection.data.get("state") if connection is not None else None)
    if connection is None or health not in {"HEALTHY", "STALE"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "connection must be healthy before binding verification"
        )
    advertised = {str(item).upper() for item in connection.data.get("capabilities", [])}
    required = str(record.data["capability"]).upper()
    aliases = {
        "DISCOVERY": {"DISCOVERY", "INSTRUMENT_DIRECTORY", "CRYPTO.DISCOVERY", "ASSET_METADATA.READ"},
        "INSTRUMENT_DIRECTORY": {"DISCOVERY", "INSTRUMENT_DIRECTORY"},
        "QUOTE": {"QUOTE", "QUOTES", "FOREX.READ", "METALS.READ", "CRYPTO.READ"},
        "CANDLES": {"CANDLE", "CANDLES", "HISTORY", "CANDLES.READ", "HISTORY.READ"},
        "FUTURES_CHAIN": {"FUTURES_CHAIN", "CONTRACT_DETAILS"},
        "CONTRACT_DETAILS": {"CONTRACT_DETAILS", "FUTURES_CHAIN"},
        "OPEN_INTEREST": {"OPEN_INTEREST", "CFTC_COT"},
        "ECONOMIC_CALENDAR": {"ECONOMIC_CALENDAR", "CALENDAR", "NEWS", "CALENDAR.READ", "NEWS.READ", "FOREX_FACTORY.SCRAPE"},
        "MACROECONOMIC": {"MACROECONOMIC", "MACRO", "ECONOMIC", "MACRO.READ"},
        "NEWS": {"NEWS", "NEWS.READ", "SEARCH.READ"},
    }
    if advertised and not (aliases.get(required, {required}) & advertised):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"connection does not advertise a compatible {required} capability",
        )
    updated = await store.update(
        record,
        {
            **record.data,
            "verification_status": "VERIFIED",
            "verified_at": datetime.now(UTC).isoformat(),
        },
        actor_id=actor.actor_id,
        event_type="provider_binding.verified",
    )
    return updated.public()


@router.get("/instruments")
async def list_instruments(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    asset_class: Annotated[AssetClass | None, Query()] = None,
    instrument_type: Annotated[InstrumentType | None, Query()] = None,
    connection_id: Annotated[UUID | None, Query()] = None,
    capability: Annotated[MarketDataCapability | None, Query()] = None,
):
    records = await ResourceStore(db).list("typed_instrument", actor.owner_id)
    result = []
    for item in records:
        data = item.data
        if asset_class and data.get("asset_class") != asset_class.value:
            continue
        if instrument_type and data.get("instrument_type") != instrument_type.value:
            continue
        if connection_id and data.get("connection_id") != str(connection_id):
            continue
        if capability and capability.value not in data.get("capabilities", []):
            continue
        result.append(item.public())
    return result


@router.post("/research-runs", status_code=status.HTTP_202_ACCEPTED)
async def create_typed_research_run(
    payload: ResearchRunInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    await _account(store, actor, payload.account_id)
    matrix = next(
        (
            item
            for item in await store.list("research_matrix", actor.owner_id)
            if item.data.get("account_id") == str(payload.account_id)
        ),
        None,
    )
    lanes = payload.lanes or [
        ResearchLaneKey.model_validate(item)
        for item in (matrix.data["lanes"] if matrix else [lane.model_dump() for lane in ALL_LANES])
        if item.get("enabled", True)
    ]
    data = {
        "account_id": str(payload.account_id),
        "matrix_version": int(matrix.data.get("version", 1)) if matrix else 1,
        "lanes": [lane.model_dump(mode="json") for lane in lanes],
        "lane_results": [],
        "source_cut_refs": [],
        "trigger": "MANUAL",
    }
    record = await store.create(
        "research_run",
        actor.owner_id,
        data,
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="research.queued",
    )
    run_research_cycle.apply_async(args=[str(record.id)], countdown=1)
    return record.public()


@router.get("/research-runs")
async def list_typed_research_runs(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    account_id: Annotated[UUID | None, Query()] = None,
):
    records = await ResourceStore(db).list("research_run", actor.owner_id)
    return [
        item.public()
        for item in records
        if item.data.get("lanes")
        and (account_id is None or item.data.get("account_id") == str(account_id))
    ]


@router.get("/research-runs/{run_id}")
async def get_typed_research_run(
    run_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await ResourceStore(db).get("research_run", run_id, actor.owner_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "research run not found")
    return record.public()
