from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.news.forex_factory import DEFAULT_FOREX_FACTORY_FEED
from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from modules.connections.models import (
    PROVIDER_LABELS,
    ConnectionProfile,
    ConnectionProvider,
)
from modules.connections.resolution import resolve_connection
from modules.connections.testing import probe_connection, twelve_data_check_due
from modules.credentials.vault import EnvelopeCipher
from modules.identity.authorization import Actor, Role
from modules.research.forex_factory_archive import ForexFactoryArchive
from modules.research.forex_factory_service import scrape_and_archive_forex_factory
from modules.research.scheduling import (
    default_schedule,
    next_run_at,
    normalize_schedule,
    schedule_timezone,
)
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


class ResearchScheduleInput(BaseModel):
    enabled: bool = True
    run_at: str = "05:00"
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))

    @field_validator("run_at")
    @classmethod
    def validate_run_at(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("run_at must use HH:MM 24-hour format") from exc
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        schedule_timezone(value)
        return value

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 (Monday) through 6 (Sunday)")
        return sorted(set(value))

    @model_validator(mode="after")
    def require_weekday_for_enabled_schedule(self) -> ResearchScheduleInput:
        if self.enabled and not self.weekdays:
            raise ValueError("an enabled schedule must include at least one weekday")
        return self


class CredentialInput(BaseModel):
    name: str
    provider: str
    purpose: str
    secret: str = Field(min_length=1)


class ConnectionInput(ConnectionProfile):
    pass


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


def _credential_status_for_probe(probe_status: str) -> str:
    return "ACTIVE" if probe_status in {"HEALTHY", "STALE"} else "INVALID"


def _default_research_schedule() -> dict[str, Any]:
    settings = get_settings()
    return default_schedule(
        enabled=settings.research_schedule_enabled,
        run_at=f"{settings.research_schedule_hour_utc:02d}:{settings.research_schedule_minute_utc:02d}",
    )


def _default_forex_factory_schedule() -> dict[str, Any]:
    settings = get_settings()
    return default_schedule(
        enabled=settings.forex_factory_schedule_enabled,
        run_at=f"{settings.forex_factory_schedule_hour_utc:02d}:{settings.forex_factory_schedule_minute_utc:02d}",
    )


async def _sync_credential_status(
    store: ResourceStore,
    connection: Any,
    probe_status: str,
    actor: Actor,
) -> None:
    credential_id = connection.data.get("credential_id")
    if not credential_id:
        return
    credential = await store.get("credential", UUID(str(credential_id)), actor.owner_id)
    if credential is None:
        return
    await store.update(
        credential,
        {
            **credential.data,
            "status": _credential_status_for_probe(probe_status),
            "last_tested": datetime.now(UTC).isoformat(),
            "last_test_result": probe_status,
        },
        actor_id=actor.actor_id,
        event_type="credential.provider_tested",
    )


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
        {
            **payload.model_dump(mode="json"),
            "research_schedule": _default_research_schedule(),
            "forex_factory_schedule": _default_forex_factory_schedule(),
        },
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
        record,
        {
            **payload.model_dump(mode="json"),
            "research_schedule": record.data.get("research_schedule", _default_research_schedule()),
            "forex_factory_schedule": record.data.get(
                "forex_factory_schedule", _default_forex_factory_schedule()
            ),
        },
        actor_id=actor.actor_id,
    )
    return updated.public()


@router.get("/accounts/{account_id}/research-schedule")
async def get_account_research_schedule(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await ResourceStore(db).get("account", account_id, actor.owner_id)
    if record is None or record.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    schedule = normalize_schedule(
        record.data.get("research_schedule"), fallback=_default_research_schedule()
    )
    upcoming = next_run_at(schedule)
    return {
        "account_id": str(record.id),
        **schedule,
        "next_run_at": upcoming.isoformat() if upcoming else None,
    }


@router.put("/accounts/{account_id}/research-schedule")
async def update_account_research_schedule(
    account_id: UUID,
    payload: ResearchScheduleInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    record = await store.get("account", account_id, actor.owner_id)
    if record is None or record.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    schedule = payload.model_dump(mode="json")
    updated = await store.update(
        record,
        {**record.data, "research_schedule": schedule},
        actor_id=actor.actor_id,
        event_type="account.research_schedule_updated",
    )
    upcoming = next_run_at(schedule)
    return {
        "account_id": str(updated.id),
        **schedule,
        "next_run_at": upcoming.isoformat() if upcoming else None,
    }


@router.get("/accounts/{account_id}/forex-factory-schedule")
async def get_account_forex_factory_schedule(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await ResourceStore(db).get("account", account_id, actor.owner_id)
    if record is None or record.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    schedule = normalize_schedule(
        record.data.get("forex_factory_schedule"), fallback=_default_forex_factory_schedule()
    )
    upcoming = next_run_at(schedule)
    return {
        "account_id": str(record.id),
        **schedule,
        "next_run_at": upcoming.isoformat() if upcoming else None,
    }


@router.put("/accounts/{account_id}/forex-factory-schedule")
async def update_account_forex_factory_schedule(
    account_id: UUID,
    payload: ResearchScheduleInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    record = await store.get("account", account_id, actor.owner_id)
    if record is None or record.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    schedule = payload.model_dump(mode="json")
    updated = await store.update(
        record,
        {**record.data, "forex_factory_schedule": schedule},
        actor_id=actor.actor_id,
        event_type="account.forex_factory_schedule_updated",
    )
    upcoming = next_run_at(schedule)
    return {
        "account_id": str(updated.id),
        **schedule,
        "next_run_at": upcoming.isoformat() if upcoming else None,
    }


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: UUID,
    actor: Annotated[Actor, Depends(require_step_up("broker.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    record = await store.get("account", account_id, actor.owner_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    updated = await store.update(
        record,
        {**record.data, "active": False, "deleted_at": datetime.now(UTC).isoformat()},
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="account.deleted",
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
    for connection in await store.list("connection", actor.owner_id):
        if str(connection.data.get("credential_id")) != str(item.id):
            continue
        await store.update(
            connection,
            {
                **connection.data,
                "health": "UNTESTED",
                "last_checked": None,
                "last_error": None,
            },
            actor_id=actor.actor_id,
            event_type="connection.credential_replaced",
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
    linked = [
        connection
        for connection in await store.list("connection", actor.owner_id)
        if str(connection.data.get("credential_id")) == str(item.id)
    ]
    if linked:
        outcomes: list[str] = []
        for connection in linked:
            twelve_data_cached = connection.data.get(
                "provider"
            ) == ConnectionProvider.TWELVE_DATA.value and not twelve_data_check_due(
                connection.data.get("last_checked")
            )
            if twelve_data_cached:
                outcomes.append(str(connection.data.get("health", "STALE")))
                continue
            try:
                resolved = await resolve_connection(db, actor.owner_id, connection.id)
                result = await probe_connection(resolved.profile, resolved.secret)
            except (LookupError, RuntimeError, ValueError) as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
            outcomes.append(result.status)
            await store.update(
                connection,
                {
                    **connection.data,
                    "health": result.status,
                    "last_checked": result.checked_at,
                    "last_success": (
                        result.checked_at
                        if result.status == "HEALTHY"
                        else connection.data.get("last_success")
                    ),
                    "capabilities": result.capabilities,
                    "fresh": result.fresh,
                    "writes": result.writes,
                    "last_error": result.safe_message,
                },
                actor_id=actor.actor_id,
                event_type="connection.health_changed",
            )
        state = "ACTIVE" if all(item in {"HEALTHY", "STALE"} for item in outcomes) else "INVALID"
    else:
        try:
            _cipher().decrypt(actor.owner_id, item.data["envelope"])
            state = "ACTIVE"
        except Exception:  # noqa: BLE001 - KMS/vault failure maps to a safe public state
            state = "INVALID"
    updated = await store.update(
        item,
        {
            **item.data,
            "status": state,
            "last_tested": datetime.now(UTC).isoformat(),
            "last_test_result": state,
        },
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


@router.get("/connection-providers")
async def connection_providers(_: Annotated[Actor, Depends(current_actor)]):
    return [
        {
            "id": provider.value,
            "label": PROVIDER_LABELS[provider],
            "credential_required": provider
            in {
                ConnectionProvider.TWELVE_DATA,
                ConnectionProvider.FRED,
                ConnectionProvider.SERPAPI,
                ConnectionProvider.MT5_BRIDGE,
            },
        }
        for provider in ConnectionProvider
    ]


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    if payload.credential_id is not None:
        credential = await store.get("credential", payload.credential_id, actor.owner_id)
        if credential is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "credential not found")
        if credential.data.get("provider") != payload.provider.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "credential provider does not match connection provider",
            )
    item = await ResourceStore(db).create(
        "connection",
        actor.owner_id,
        {
            **payload.model_dump(mode="json"),
            "health": "UNTESTED",
            "last_success": None,
            "last_checked": None,
            "capabilities": [],
        },
        state="ACTIVE" if payload.active else "DISABLED",
        actor_id=actor.actor_id,
        event_type="connection.created",
    )
    return item.public()


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: UUID,
    payload: ConnectionInput,
    actor: Annotated[Actor, Depends(require_step_up("connection.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("connection", connection_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    if payload.credential_id is not None:
        credential = await store.get("credential", payload.credential_id, actor.owner_id)
        if credential is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "credential not found")
        if credential.data.get("provider") != payload.provider.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "credential provider does not match connection provider",
            )
    updated = await store.update(
        item,
        {
            **payload.model_dump(mode="json"),
            "health": "UNTESTED",
            "last_success": item.data.get("last_success"),
            "last_checked": None,
            "capabilities": item.data.get("capabilities", []),
        },
        state="ACTIVE" if payload.active else "DISABLED",
        actor_id=actor.actor_id,
        event_type="connection.updated",
    )
    return updated.public()


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: UUID,
    actor: Annotated[Actor, Depends(require_step_up("connection.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remove a configured source without erasing its audit history."""
    store = ResourceStore(db)
    item = await store.get("connection", connection_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    updated = await store.update(
        item,
        {**item.data, "active": False, "deleted_at": datetime.now(UTC).isoformat()},
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="connection.deleted",
    )
    return updated.public()


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
    twelve_data_cached = item.data.get(
        "provider"
    ) == ConnectionProvider.TWELVE_DATA.value and not twelve_data_check_due(
        item.data.get("last_checked")
    )
    if twelve_data_cached:
        checked_at = datetime.fromisoformat(str(item.data["last_checked"]).replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        return {
            **item.public(),
            "health_cached": True,
            "next_check_at": (checked_at.astimezone(UTC) + timedelta(hours=1)).isoformat(),
        }
    try:
        resolved = await resolve_connection(db, actor.owner_id, connection_id)
        result = await probe_connection(resolved.profile, resolved.secret)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    data = {
        **item.data,
        "health": result.status,
        "last_success": (
            result.checked_at if result.status == "HEALTHY" else item.data.get("last_success")
        ),
        "last_checked": result.checked_at,
        "latency_ms": result.latency_ms,
        "capabilities": result.capabilities,
        "adapter_version": result.version,
        "fresh": result.fresh,
        "writes": result.writes,
        "last_error": result.safe_message,
    }
    updated = await store.update(
        item, data, actor_id=actor.actor_id, event_type="connection.health_changed"
    )
    await _sync_credential_status(store, item, result.status, actor)
    return updated.public()


@router.post("/connections/{connection_id}/forex-factory/scrape")
async def scrape_forex_factory(
    connection_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Fetch and normalize the configured Forex Factory calendar feed on demand."""
    store = ResourceStore(db)
    connection = await store.get("connection", connection_id, actor.owner_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    if connection.data.get("provider") != ConnectionProvider.FOREX_FACTORY.value:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "connection is not a Forex Factory scraper",
        )
    feed_url = str(
        connection.data.get("configuration", {}).get("feed_url", DEFAULT_FOREX_FACTORY_FEED)
    )
    try:
        archive = ForexFactoryArchive(get_settings().research_artifact_root)
        reference = await scrape_and_archive_forex_factory(
            owner_id=actor.owner_id,
            feed_url=feed_url,
            archive=archive,
        )
    except (OSError, httpx.HTTPError, RuntimeError, ValueError) as exc:
        checked_at = datetime.now(UTC).isoformat()
        await store.update(
            connection,
            {
                **connection.data,
                "health": "OFFLINE",
                "last_checked": checked_at,
                "last_error": f"{type(exc).__name__}: scraper failed",
            },
            actor_id=actor.actor_id,
            event_type="connection.forex_factory_scrape_failed",
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Forex Factory scraper failed: {type(exc).__name__}",
        ) from exc
    fetched_at = datetime.now(UTC).isoformat()
    health = "HEALTHY" if reference.event_count else "STALE"
    await store.update(
        connection,
        {
            **connection.data,
            "health": health,
            "last_checked": (
                fetched_at if not reference.skipped else connection.data.get("last_checked")
            ),
            "last_success": (
                fetched_at if reference.event_count else connection.data.get("last_success")
            ),
            "capabilities": ["news.read", "calendar.read", "forex_factory.scrape"],
            "fresh": bool(reference.event_count),
            "last_error": None,
        },
        actor_id=actor.actor_id,
        event_type=(
            "connection.forex_factory_scrape_skipped"
            if reference.skipped
            else "connection.forex_factory_scraped"
        ),
    )
    return {
        "connection_id": str(connection.id),
        "provider": ConnectionProvider.FOREX_FACTORY.value,
        "feed_url": feed_url,
        "fetched_at": fetched_at,
        "count": reference.event_count,
        "health": health,
        "events": reference.events,
        "period_key": reference.period_key,
        "period_start": reference.period_start.isoformat(),
        "period_end": reference.period_end.isoformat(),
        "archive_path": reference.relative_path,
        "skipped": reference.skipped,
        "message": reference.message,
    }


@router.get("/connections/{connection_id}/forex-factory/archive")
async def list_forex_factory_archive(
    connection_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    connection = await ResourceStore(db).get("connection", connection_id, actor.owner_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connection not found")
    if connection.data.get("provider") != ConnectionProvider.FOREX_FACTORY.value:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "connection is not a Forex Factory scraper",
        )
    archive = ForexFactoryArchive(get_settings().research_artifact_root)
    return [
        {
            "period_key": item.period_key,
            "period_start": item.period_start.isoformat(),
            "period_end": item.period_end.isoformat(),
            "archive_path": item.relative_path,
            "count": item.event_count,
        }
        for item in archive.list_periods(actor.owner_id)
    ]


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


@router.delete("/prop-rulesets/{rule_id}")
async def delete_prop_ruleset(
    rule_id: UUID,
    actor: Annotated[Actor, Depends(require_step_up("hard_rule.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("prop_ruleset", rule_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prop-firm ruleset not found")
    updated = await store.update(
        item,
        {**item.data, "deleted_at": datetime.now(UTC).isoformat()},
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="prop_ruleset.deleted",
    )
    return updated.public()


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


@router.delete("/guardrails/{rule_id}")
async def delete_guardrail(
    rule_id: UUID,
    actor: Annotated[Actor, Depends(require_step_up("hard_rule.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("guardrail", rule_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "guardrail not found")
    updated = await store.update(
        item,
        {**item.data, "deleted_at": datetime.now(UTC).isoformat()},
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="guardrail.deleted",
    )
    return updated.public()


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
