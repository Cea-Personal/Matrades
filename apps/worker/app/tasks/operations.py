from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from apps.worker.app.celery_app import celery_app
from modules.credentials.vault import EnvelopeCipher
from modules.journal.models import JournalEntry, JournalEntryKind
from modules.knowledge.ingestion import build_source_data
from modules.notifications.providers import NotificationDeliveryError, send_notification
from modules.performance.metrics import analytics
from modules.performance.models import PerformanceRecord
from modules.performance.strategy_health import evaluate_health
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.domain_types import utc_now
from packages.shared.outbox import OutboxRecord
from packages.shared.store import AuditRecord, ResourceRecord, ResourceStore

MATERIAL_TRADE_AGGREGATES = frozenset(
    {
        "active_trade",
        "trade_plan",
        "execution_command",
        "broker_order",
        "broker_fill",
        "broker_position",
    }
)


async def _queue_journal_index(
    *,
    store: ResourceStore,
    owner_id: UUID,
    entry: JournalEntry,
) -> None:
    """Create the durable, generation-scoped request to index an entry."""
    event_key = uuid5(NAMESPACE_URL, f"journal-index:{entry.id}:1")
    if await store.get("journal_index_request", event_key, owner_id) is not None:
        return
    from packages.contracts.events import EventEnvelope, JournalIndexPayload

    request = await store.create(
        "journal_index_request",
        owner_id,
        {"journal_entry_id": str(entry.id), "generation": 1},
        state="QUEUED",
        record_id=event_key,
        event_type="journal.index_requested",
    )
    store.session.add(
        OutboxRecord(
            event_id=event_key,
            owner_id=owner_id,
            event_type="journal.index_requested",
            payload=EventEnvelope(
                event_id=event_key,
                event_type="journal.index_requested",
                owner_id=owner_id,
                aggregate_id=request.id,
                aggregate_version=request.version,
                payload=JournalIndexPayload(
                    journal_entry_id=entry.id, indexing_state="QUEUED"
                ).model_dump(mode="json"),
            ).json_bytes(),
        )
    )


async def _project_journal(event_id: UUID) -> dict:
    async with unit_of_work() as session:
        audit = await session.get(AuditRecord, event_id)
        if audit is None:
            raise RuntimeError("audit event not found")
        store = ResourceStore(session)
        entry_id = uuid5(NAMESPACE_URL, f"journal:{audit.id}")
        existing = await store.get("journal_entry", entry_id, audit.owner_id)
        if existing is not None:
            return {
                "event_id": str(event_id),
                "journal_entry_id": str(entry_id),
                "idempotent": True,
            }
        kind = (
            JournalEntryKind.EXECUTION
            if audit.event_type.startswith("execution.")
            else JournalEntryKind.TRADE_PLAN
            if audit.aggregate_type == "trade_plan"
            else JournalEntryKind.POSITION_UPDATE
            if audit.aggregate_type in {"active_trade", "broker_position"}
            else JournalEntryKind.SYSTEM
        )
        entry = JournalEntry(
            id=entry_id,
            owner_id=audit.owner_id,
            trade_id=audit.aggregate_id if audit.aggregate_type == "active_trade" else None,
            trade_plan_id=audit.aggregate_id if audit.aggregate_type == "trade_plan" else None,
            kind=kind,
            text=audit.event_type,
            facts={
                "observation_label": "OBSERVATION",
                "event_type": audit.event_type,
                "aggregate_type": audit.aggregate_type,
                "aggregate_id": str(audit.aggregate_id) if audit.aggregate_id else None,
                "evidence": audit.evidence,
            },
            source_event_id=audit.id,
            recorded_at=audit.created_at,
        )
        await store.create(
            "journal_entry",
            audit.owner_id,
            entry.model_dump(mode="json"),
            state="INDEX_QUEUED",
            record_id=entry.id,
            event_type="journal.observation_projected",
        )
        await _queue_journal_index(store=store, owner_id=audit.owner_id, entry=entry)

        terminal_summary_id: UUID | None = None
        if (
            audit.aggregate_type == "active_trade"
            and audit.aggregate_id is not None
            and audit.evidence.get("state") == "CLOSED"
        ):
            terminal_summary_id = uuid5(NAMESPACE_URL, f"journal-terminal:{audit.aggregate_id}")
            if await store.get("journal_entry", terminal_summary_id, audit.owner_id) is None:
                trade_entries = [
                    item
                    for item in await store.list("journal_entry", audit.owner_id)
                    if item.data.get("trade_id") == str(audit.aggregate_id)
                ]
                trade_entries.sort(key=lambda item: (item.created_at, str(item.id)))
                event_ids = [
                    str(item.data["source_event_id"])
                    for item in trade_entries
                    if item.data.get("source_event_id")
                ]
                summary = JournalEntry(
                    id=terminal_summary_id,
                    owner_id=audit.owner_id,
                    trade_id=audit.aggregate_id,
                    kind=JournalEntryKind.POST_TRADE,
                    text=f"Terminal trade outcome: {audit.event_type}",
                    facts={
                        "observation_label": "INFERENCE",
                        "terminal_event": audit.event_type,
                        "event_range": event_ids,
                        "terminal_evidence": audit.evidence,
                    },
                    source_event_id=audit.id,
                    recorded_at=audit.created_at,
                )
                await store.create(
                    "journal_entry",
                    audit.owner_id,
                    summary.model_dump(mode="json"),
                    state="INDEX_QUEUED",
                    record_id=summary.id,
                    event_type="journal.terminal_summary_projected",
                )
                await _queue_journal_index(store=store, owner_id=audit.owner_id, entry=summary)

        return {
            "event_id": str(event_id),
            "journal_entry_id": str(entry.id),
            "terminal_summary_id": str(terminal_summary_id) if terminal_summary_id else None,
            "projected": True,
        }


@celery_app.task(name="apps.worker.app.tasks.operations.project_journal")
def project_journal(event_id: str) -> dict:
    return asyncio.run(_project_journal(UUID(event_id)))


async def _project_pending_journal_events(limit: int = 100) -> int:
    """Recover material events committed before a worker restart."""
    async with unit_of_work() as session:
        events = list(
            (
                await session.scalars(
                    select(AuditRecord)
                    .where(AuditRecord.aggregate_type.in_(MATERIAL_TRADE_AGGREGATES))
                    .order_by(AuditRecord.created_at.asc())
                    .limit(limit * 4)
                )
            ).all()
        )
        existing = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(ResourceRecord.kind == "journal_entry")
                )
            ).all()
        )
        projected_ids = {
            str(entry.data.get("source_event_id"))
            for entry in existing
            if entry.data.get("source_event_id")
        }
        pending = [event.id for event in events if str(event.id) not in projected_ids][:limit]
    for event_id in pending:
        await _project_journal(event_id)
    return len(pending)


@celery_app.task(name="apps.worker.app.tasks.operations.project_pending_journal_events")
def project_pending_journal_events(limit: int = 100) -> dict:
    return {"projected": asyncio.run(_project_pending_journal_events(limit))}


async def _index_journal_entries(limit: int = 100) -> int:
    async with unit_of_work() as session:
        events = list(
            (
                await session.scalars(
                    select(OutboxRecord)
                    .where(
                        OutboxRecord.event_type == "journal.index_requested",
                        OutboxRecord.published_at.is_(None),
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        store = ResourceStore(session)
        indexed = 0
        for event in events:
            payload = json.loads(event.payload)
            entry_id = UUID(str(payload["payload"]["journal_entry_id"]))
            entry = await store.get("journal_entry", entry_id, event.owner_id)
            if entry is None:
                event.published_at = utc_now()
                continue
            source_id = uuid5(NAMESPACE_URL, f"journal-knowledge:{entry_id}")
            if await store.get("knowledge_source", source_id, event.owner_id) is None:
                await store.create(
                    "knowledge_source",
                    event.owner_id,
                    {
                        **build_source_data(
                            name=f"Live journal — {entry.data.get('text', entry_id)}",
                            content=json.dumps(entry.data, default=str),
                            category="live-journal",
                            tags=["journal", "live-trade"],
                            source_kind="LIVE_JOURNAL",
                            external_id=str(entry_id),
                        ),
                        "journal_entry_id": str(entry_id),
                    },
                    record_id=source_id,
                    event_type="journal.knowledge_indexed",
                )
            await store.update(
                entry,
                {
                    **entry.data,
                    "knowledge_index_state": "INDEXED",
                    "indexed_at": utc_now().isoformat(),
                },
                state="INDEXED",
                event_type="journal.index_completed",
            )
            event.published_at = utc_now()
            event.attempts += 1
            indexed += 1
        return indexed


@celery_app.task(name="apps.worker.app.tasks.operations.index_journal_entries")
def index_journal_entries(limit: int = 100) -> dict:
    return {"indexed": asyncio.run(_index_journal_entries(limit))}


async def _rollup_performance(owner_id: UUID) -> dict:
    async with unit_of_work() as session:
        store = ResourceStore(session)
        created = 0
        for trade in await store.list("active_trade", owner_id):
            if trade.state != "CLOSED":
                continue
            position = dict(trade.data.get("broker_position", {}))
            plan_id = trade.data.get("trade_plan_id")
            plan = await store.get("trade_plan", UUID(str(plan_id)), owner_id) if plan_id else None
            if plan is None:
                continue
            observation_id = uuid5(NAMESPACE_URL, f"performance:{trade.id}:{trade.version}")
            if await store.get("performance_observation", observation_id, owner_id):
                continue
            construction = dict(plan.data.get("construction", {}))
            risk = dict(plan.data.get("risk", {})).get("snapshot", {})
            record = PerformanceRecord(
                id=observation_id,
                owner_id=owner_id,
                trade_id=trade.id,
                strategy_version_id=UUID(str(plan.data["strategy_version_id"])),
                account_id=UUID(str(plan.data["account_id"])),
                instrument=str(construction.get("instrument", position.get("symbol", "UNKNOWN"))),
                category=str(construction.get("asset_class", "UNKNOWN")),
                regime=str(plan.data.get("regime", "UNCLASSIFIED")),
                session=str(plan.data.get("session", "UNKNOWN")),
                pnl=position.get("pnl", "0"),
                risk=risk.get("candidate_trade_risk", "1"),
                asset_class=construction.get("asset_class"),
                instrument_type=construction.get("instrument_type"),
                venue_instrument_id=construction.get("venue_instrument_id"),
                futures_contract_id=construction.get("futures_contract_id"),
                quantity_unit=construction.get("quantity_unit"),
                commissions=position.get("fees", "0"),
                closed_at=trade.updated_at,
                source_refs=(f"active_trade:{trade.id}:v{trade.version}",),
            )
            await store.create(
                "performance_observation",
                owner_id,
                record.model_dump(mode="json"),
                state="COMPLETED",
                record_id=record.id,
                event_type="performance.observation_projected",
            )
            created += 1
        return {"owner_id": str(owner_id), "created": created}


@celery_app.task(name="apps.worker.app.tasks.operations.rollup_performance")
def rollup_performance(owner_id: str) -> dict:
    return asyncio.run(_rollup_performance(UUID(owner_id)))


async def _evaluate_strategy_health(version_id: UUID) -> dict:
    async with unit_of_work() as session:
        strategy = await session.get(ResourceRecord, version_id)
        if strategy is None or strategy.kind != "strategy_version":
            raise RuntimeError("strategy version not found")
        store = ResourceStore(session)
        records = [
            PerformanceRecord.model_validate(item.data)
            for item in await store.list("performance_observation", strategy.owner_id)
            if item.data.get("strategy_version_id") == str(version_id)
            and item.data.get("evidence_class") == "LIVE"
        ]
        metrics = analytics(records)
        work = evaluate_health(
            {
                "drawdown": float(metrics.get("max_drawdown", 0)),
                "expectancy": float(metrics.get("expectancy", 0)),
            },
            str(version_id),
        )
        work_id = uuid5(NAMESPACE_URL, f"strategy-health:{version_id}:{strategy.version}")
        if await store.get("strategy_health_work", work_id, strategy.owner_id) is None:
            await store.create(
                "strategy_health_work",
                strategy.owner_id,
                {
                    **work.model_dump(mode="json"),
                    "metrics": {key: str(value) for key, value in metrics.items()},
                },
                state=work.action.value,
                record_id=work_id,
                event_type="strategy_health.work_created",
            )
        return {**work.model_dump(mode="json"), "active_mutated": False}


@celery_app.task(name="apps.worker.app.tasks.operations.evaluate_strategy_health")
def evaluate_strategy_health(version_id: str) -> dict:
    return asyncio.run(_evaluate_strategy_health(UUID(version_id)))


async def _deliver_notification(notification_id: UUID) -> dict:
    async with unit_of_work() as session:
        notification = await session.get(ResourceRecord, notification_id)
        if notification is None or notification.kind != "notification":
            raise RuntimeError("notification not found")
        store = ResourceStore(session)
        preferences = await store.list("notification_preferences", notification.owner_id)
        preference = (
            preferences[0].data
            if preferences
            else {
                "in_app": True,
                "telegram": False,
                "pushover": False,
                "urgent_only_external": True,
            }
        )
        channels = await store.list("notification_channel", notification.owner_id)
        credentials = {
            str(item.id): item for item in await store.list("credential", notification.owner_id)
        }
        data = notification.data
        title = str(data.get("title") or data.get("event_type") or "Matrades notification")
        message = str(data.get("message") or data.get("body") or "")
        urgency = str(data.get("urgency") or data.get("priority") or "NORMAL").upper()
        receipts: list[dict] = []
        failures: list[dict] = []
        for channel in channels:
            if channel.state != "ACTIVE" or not channel.data.get("enabled", True):
                continue
            requested_channel_id = data.get("channel_id")
            if requested_channel_id and str(channel.id) != str(requested_channel_id):
                continue
            provider = str(channel.data.get("provider", "")).upper()
            if not preference.get(provider.lower(), False):
                continue
            if preference.get("urgent_only_external", True) and urgency not in {
                "URGENT",
                "CRITICAL",
                "HIGH",
            }:
                continue
            credential = credentials.get(str(channel.data.get("credential_id")))
            try:
                if credential is None:
                    raise NotificationDeliveryError("notification credential unavailable")
                secret = EnvelopeCipher(settings.secret_key.get_secret_value().encode()).decrypt(
                    notification.owner_id, credential.data["envelope"]
                )
                receipts.append(
                    await send_notification(
                        provider,
                        secret,
                        str(channel.data.get("destination", "")),
                        title=title,
                        message=message,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one bad channel must not block inbox delivery
                failures.append(
                    {"channel_id": str(channel.id), "provider": provider, "error": str(exc)[:180]}
                )
        state = "DEGRADED" if failures else "DELIVERED"
        updated = await store.update(
            notification,
            {
                **data,
                "delivery_state": state,
                "delivered_at": datetime.now(UTC).isoformat()
                if not failures
                else data.get("delivered_at"),
                "delivery_receipts": receipts,
                "delivery_failures": failures,
            },
            state=state,
            event_type="notification.delivery_completed"
            if not failures
            else "notification.delivery_degraded",
        )
        return {
            "notification_id": str(updated.id),
            "state": state,
            "receipts": receipts,
            "failures": failures,
        }


@celery_app.task(name="apps.worker.app.tasks.operations.deliver_notification")
def deliver_notification(notification_id: str) -> dict:
    return asyncio.run(_deliver_notification(UUID(notification_id)))


async def _drain_notification_outbox(limit: int = 100) -> list[str]:
    async with unit_of_work() as session:
        records = list(
            (
                await session.scalars(
                    select(OutboxRecord)
                    .where(
                        OutboxRecord.event_type == "notification.delivery_requested",
                        OutboxRecord.published_at.is_(None),
                    )
                    .order_by(OutboxRecord.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        notification_ids: list[str] = []
        for record in records:
            payload = json.loads(record.payload)
            notification_ids.append(str(payload["aggregate_id"]))
            record.attempts += 1
            record.published_at = utc_now()
        await session.flush()
        return notification_ids


@celery_app.task(name="apps.worker.app.tasks.operations.drain_notification_outbox")
def drain_notification_outbox(limit: int = 100) -> dict:
    notification_ids = asyncio.run(_drain_notification_outbox(limit))
    for notification_id in notification_ids:
        deliver_notification.delay(notification_id)
    return {"published": len(notification_ids), "notification_ids": notification_ids}
