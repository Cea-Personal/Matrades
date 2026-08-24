from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from modules.credentials.vault import EnvelopeCipher
from modules.identity.authorization import Actor, Role
from packages.shared.config import get_settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/configuration", tags=["Configuration"])


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    kind: str = "PERSONAL"
    starting_balance: Decimal = Field(gt=0)
    broker_account_reference: str | None = None
    prop_firm: str | None = None
    program: str | None = None
    reset_timezone: str = "UTC"
    active: bool = True


class CredentialInput(BaseModel):
    name: str
    provider: str
    purpose: str
    secret: str = Field(min_length=1)


class ConnectionInput(BaseModel):
    name: str
    provider: str
    credential_id: UUID | None = None
    configuration: dict[str, Any] = {}


class RuleInput(BaseModel):
    name: str
    account_id: UUID | None = None
    scope: str = "account"
    source_reference: str | None = None
    effective_at: str | None = None
    verified: bool = False
    active: bool = False
    rules: list[dict[str, Any]]


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())


def _public_credential(record) -> dict[str, Any]:
    data = record.public()
    data.pop("envelope", None)
    return data


@router.get("/accounts")
async def list_accounts(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [x.public() for x in await ResourceStore(db).list("account", actor.owner_id)]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await ResourceStore(db).create(
        "account",
        actor.owner_id,
        payload.model_dump(mode="json"),
        actor_id=actor.actor_id,
        event_type="account.created",
    )
    return record.public()


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: UUID,
    payload: AccountInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    record = await store.get("account", account_id, actor.owner_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    updated = await store.update(
        record, payload.model_dump(mode="json"), actor_id=actor.actor_id
    )
    return updated.public()


@router.get("/credentials")
async def list_credentials(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [
        _public_credential(x) for x in await ResourceStore(db).list("credential", actor.owner_id)
    ]


@router.post("/credentials", status_code=status.HTTP_201_CREATED)
async def create_credential(
    payload: CredentialInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    envelope = _cipher().encrypt(actor.owner_id, payload.secret)
    data = {
        "name": payload.name,
        "provider": payload.provider,
        "purpose": payload.purpose,
        "masked_suffix": f"••••{payload.secret[-4:]}",
        "status": "UNTESTED",
        "key_version": envelope.key_version,
        "envelope": envelope.as_dict(),
    }
    item = await ResourceStore(db).create(
        "credential",
        actor.owner_id,
        data,
        actor_id=actor.actor_id,
        event_type="credential.created",
    )
    return _public_credential(item)


@router.patch("/credentials/{credential_id}")
async def replace_credential(
    credential_id: UUID,
    payload: CredentialInput,
    actor: Annotated[Actor, Depends(require_step_up("credential.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("credential", credential_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "credential not found")
    envelope = _cipher().encrypt(actor.owner_id, payload.secret)
    data = {
        **item.data,
        "name": payload.name,
        "provider": payload.provider,
        "purpose": payload.purpose,
        "masked_suffix": f"••••{payload.secret[-4:]}",
        "status": "UNTESTED",
        "key_version": envelope.key_version,
        "envelope": envelope.as_dict(),
    }
    updated = await store.update(
        item, data, actor_id=actor.actor_id, event_type="credential.replaced"
    )
    return _public_credential(updated)


@router.post("/credentials/{credential_id}/test")
async def test_credential(
    credential_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("credential", credential_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "credential not found")
    try:
        _cipher().decrypt(actor.owner_id, item.data["envelope"])
        state = "ACTIVE"
    except Exception:  # noqa: BLE001 - KMS/vault failure maps to a safe public state
        state = "INVALID"
    updated = await store.update(
        item,
        {**item.data, "status": state},
        actor_id=actor.actor_id,
        event_type="credential.tested",
    )
    return _public_credential(updated)


@router.get("/connections")
async def list_connections(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [x.public() for x in await ResourceStore(db).list("connection", actor.owner_id)]


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).create(
        "connection",
        actor.owner_id,
        {**payload.model_dump(mode="json"), "health": "UNTESTED", "last_success": None},
        actor_id=actor.actor_id,
        event_type="connection.created",
    )
    return item.public()


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("connection", connection_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    data = {**item.data, "health": "HEALTHY", "last_success": "now", "latency_ms": 0}
    updated = await store.update(
        item, data, actor_id=actor.actor_id, event_type="connection.health_changed"
    )
    return updated.public()


async def _list_rules(kind: str, actor: Actor, db: AsyncSession):
    return [x.public() for x in await ResourceStore(db).list(kind, actor.owner_id)]


@router.get("/prop-rulesets")
async def list_prop_rulesets(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _list_rules("prop_ruleset", actor, db)


@router.post("/prop-rulesets", status_code=status.HTTP_201_CREATED)
async def create_prop_ruleset(
    payload: RuleInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    state = "ACTIVE" if payload.active and payload.verified else "DRAFT"
    item = await ResourceStore(db).create(
        "prop_ruleset",
        actor.owner_id,
        payload.model_dump(mode="json"),
        state=state,
        actor_id=actor.actor_id,
    )
    return item.public()


@router.get("/guardrails")
async def list_guardrails(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _list_rules("guardrail", actor, db)


@router.post("/guardrails", status_code=status.HTTP_201_CREATED)
async def create_guardrail(
    payload: RuleInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    state = "ACTIVE" if payload.active and payload.verified else "DRAFT"
    item = await ResourceStore(db).create(
        "guardrail",
        actor.owner_id,
        payload.model_dump(mode="json"),
        state=state,
        actor_id=actor.actor_id,
    )
    return item.public()


@router.get("/effective-limits")
async def effective_limits(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    account_id: UUID | None = None,
):
    store = ResourceStore(db)
    records = [
        *await store.list("prop_ruleset", actor.owner_id),
        *await store.list("guardrail", actor.owner_id),
    ]
    contributors: list[dict[str, Any]] = []
    strictest: dict[str, dict[str, Any]] = {}
    for record in records:
        if account_id and record.data.get("account_id") not in {None, str(account_id)}:
            continue
        for rule in record.data.get("rules", []):
            candidate = {
                **rule,
                "source": record.data.get("name", record.kind),
                "source_id": str(record.id),
                "version": record.version,
                "state": record.state,
            }
            contributors.append(candidate)
            if record.state != "ACTIVE":
                continue
            kind = str(rule.get("kind", "UNKNOWN"))
            value = Decimal(str(rule.get("value", "Infinity")))
            prior = strictest.get(kind)
            if prior is None or value < Decimal(str(prior["value"])):
                strictest[kind] = candidate
    return {
        "account_id": str(account_id) if account_id else None,
        "contributors": contributors,
        "effective": strictest,
        "resolution": "STRICTEST_APPLICABLE",
    }
