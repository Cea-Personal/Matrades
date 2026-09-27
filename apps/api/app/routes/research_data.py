"""Owner-scoped history import and quantitative evidence inspection, never trading."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.connections.models import ConnectionProvider
from modules.identity.authorization import Actor, Role
from modules.market_data.research_history import verified_import_binding
from modules.market_data.research_store import ResearchDataStore
from packages.shared.config import settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/research-data", tags=["Research data"])


class HistoryImport(BaseModel):
    account_id: UUID
    connection_id: UUID
    instrument: str = Field(min_length=1, max_length=100)
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def bounded(self):
        if not timedelta(0) < self.end_at - self.start_at <= timedelta(days=31):
            raise ValueError(
                "import at most 31 days per job; accumulated datasets support deep history"
            )
        if self.end_at > datetime.now(UTC):
            raise ValueError("cannot import future history")
        return self


@router.post("/imports", status_code=202)
async def import_history(
    payload: HistoryImport,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from apps.worker.app.tasks.research_data import ingest_research_history

    store = ResourceStore(db)
    account = await store.get("account", payload.account_id, actor.owner_id)
    connection = await store.get("connection", payload.connection_id, actor.owner_id)
    if (
        account is None
        or connection is None
        or account.state == "DELETED"
        or connection.state == "DELETED"
    ):
        raise HTTPException(404, "account or connection not found")
    if connection.data.get("provider") not in {
        ConnectionProvider.DUKASCOPY.value,
        ConnectionProvider.CCXT.value,
        ConnectionProvider.YAHOO_FINANCE.value,
    }:
        raise HTTPException(422, "use a configured public research history connection")
    if not connection.data.get("active", True):
        raise HTTPException(409, "research connection is disabled")
    bindings = await store.list("provider_binding", actor.owner_id)
    if not verified_import_binding(
        bindings, payload.account_id, payload.connection_id, connection.data["provider"]
    ):
        raise HTTPException(
            409, "a verified account CANDLES binding is required: HISTORY, or REFERENCE for Yahoo"
        )
    pending = [
        r
        for r in await store.list("research_data_import", actor.owner_id)
        if r.state in {"QUEUED", "INGESTING"}
    ]
    if len(pending) >= 4:
        raise HTTPException(409, "at most four concurrent history imports per owner")
    record = await store.create(
        "research_data_import",
        actor.owner_id,
        payload.model_dump(mode="json"),
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="research_data.import_queued",
    )
    ingest_research_history.apply_async(args=[str(record.id)], countdown=1)
    return record.public()


@router.get("/{kind}")
async def list_evidence(
    kind: Literal["imports", "datasets", "features", "contexts", "experiments"],
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    account_id: UUID | None = None,
):
    kinds = {
        "imports": "research_data_import",
        "datasets": "market_dataset",
        "features": "market_features",
        "contexts": "market_context",
        "experiments": "strategy_experiment",
    }
    records = await ResourceStore(db).list(kinds[kind], actor.owner_id)
    return [
        r.public()
        for r in records
        if account_id is None or r.data.get("account_id") == str(account_id)
    ]


@router.get("/experiments/{experiment_id}/results")
async def experiment_results(
    experiment_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await ResourceStore(db).get("strategy_experiment", experiment_id, actor.owner_id)
    if record is None:
        raise HTTPException(404, "experiment not found")
    import json

    return json.loads(
        ResearchDataStore(settings.research_data_root, actor.owner_id).get(record.data["archive"])
    )
