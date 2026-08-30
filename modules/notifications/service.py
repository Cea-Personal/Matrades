from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from modules.performance.models import Notification
from packages.contracts.events import EventEnvelope, NotificationPayload
from packages.shared.domain_types import utc_now
from packages.shared.outbox import OutboxRecord
from packages.shared.store import ResourceStore


class NotificationService:
    def __init__(self):
        self.items = {}
        self.preferences = {}

    def create(
        self, owner_id: UUID, kind: str, urgency: str, title: str, body: str, dedupe_key: str
    ) -> Notification:
        key = (owner_id, dedupe_key)
        if key in self.items:
            return self.items[key]
        item = Notification(
            owner_id=owner_id,
            kind=kind,
            urgency=urgency,
            title=title,
            body=body,
            dedupe_key=dedupe_key,
        )
        self.items[key] = item
        return item

    def mark(self, item: Notification, state: str) -> Notification:
        updated = item.model_copy(update={"state": state})
        self.items[(item.owner_id, item.dedupe_key)] = updated
        return updated

    def confirmed_entry(
        self,
        *,
        owner_id: UUID,
        execution_command_id: UUID,
        fill_revision: int,
        channel: str,
        instrument: str,
        quantity: str,
    ) -> Notification:
        """Create exactly one entry notification for a command/fill/channel tuple."""
        return self.create(
            owner_id,
            kind="trade_entry_confirmed",
            urgency="HIGH",
            title=f"Confirmed entry: {instrument}",
            body=f"{quantity} filled; broker state confirmed.",
            dedupe_key=f"entry:{execution_command_id}:{fill_revision}:{channel}",
        )


async def queue_confirmed_broker_notifications(
    session: AsyncSession,
    *,
    owner_id: UUID,
    command_id: UUID,
    event_kind: str,
    revision: int,
    account_id: UUID,
    instrument: str,
    quantity: Decimal,
    price: Decimal | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    strategy_version_id: UUID,
    trade_plan_id: UUID,
    broker_order_id: str | None,
    observed_at: datetime | None = None,
) -> list[UUID]:
    """Persist one notification and delivery intent per enabled channel.

    The caller invokes this only after a broker fact is reconciled as confirmed;
    uncertain acknowledgements must never enter the notification outbox.
    """
    store = ResourceStore(session)
    preference_records = await store.list("notification_preferences", owner_id)
    preferences = (
        preference_records[0].data
        if preference_records
        else {"in_app": True, "telegram": False, "pushover": False}
    )
    channels: list[tuple[str, UUID | None]] = []
    if preferences.get("in_app", True):
        channels.append(("IN_APP", None))
    for record in await store.list("notification_channel", owner_id):
        provider = str(record.data.get("provider", "")).upper()
        if (
            record.state == "ACTIVE"
            and record.data.get("enabled", True)
            and provider in {"TELEGRAM", "PUSHOVER"}
            and preferences.get(provider.lower(), False)
        ):
            channels.append((provider, record.id))
    timestamp = observed_at or utc_now()
    created: list[UUID] = []
    for channel, channel_id in channels:
        dedupe_key = f"broker:{command_id}:{event_kind}:{revision}:{channel}"
        notification_id = uuid5(NAMESPACE_URL, f"{owner_id}:{dedupe_key}")
        existing = await store.get("notification", notification_id, owner_id)
        if existing is not None:
            created.append(existing.id)
            continue
        state = "DELIVERED" if channel == "IN_APP" else "QUEUED"
        title = f"{event_kind.replace('_', ' ').title()}: {instrument}"
        body = (
            f"Account {account_id}; order {broker_order_id or 'position-confirmed'}; "
            f"quantity {quantity}; price {price or 'pending'}; Stop Loss "
            f"{stop_loss or 'unset'}; Take Profit {take_profit or 'unset'}; "
            f"strategy {strategy_version_id}; observed {timestamp.isoformat()}; "
            f"Trade Plan /automation/trade-plans/{trade_plan_id}."
        )
        notification = await store.create(
            "notification",
            owner_id,
            {
                "kind": event_kind,
                "urgency": "HIGH",
                "title": title,
                "body": body,
                "message": body,
                "dedupe_key": dedupe_key,
                "channel": channel,
                "channel_id": str(channel_id) if channel_id else None,
                "command_id": str(command_id),
                "trade_plan_id": str(trade_plan_id),
                "account_id": str(account_id),
                "broker_order_id": broker_order_id,
                "instrument": instrument,
                "quantity": str(quantity),
                "price": str(price) if price is not None else None,
                "stop_loss": str(stop_loss) if stop_loss is not None else None,
                "take_profit": str(take_profit) if take_profit is not None else None,
                "strategy_version_id": str(strategy_version_id),
                "broker_observed_at": timestamp.isoformat(),
                "delivery_state": state,
                "delivery_receipts": (
                    [{"provider": "IN_APP", "state": "DELIVERED", "at": timestamp.isoformat()}]
                    if channel == "IN_APP"
                    else []
                ),
            },
            state=state,
            record_id=notification_id,
            event_type="notification.confirmed_broker_event_queued",
        )
        created.append(notification.id)
        if channel != "IN_APP":
            event_id = uuid5(NAMESPACE_URL, f"outbox:{dedupe_key}")
            envelope = EventEnvelope(
                event_id=event_id,
                event_type="notification.delivery_requested",
                owner_id=owner_id,
                aggregate_id=notification.id,
                aggregate_version=notification.version,
                payload=NotificationPayload(
                    notification_id=notification.id,
                    channel=channel,
                    state="QUEUED",
                    idempotency_key=dedupe_key,
                ).model_dump(mode="json"),
            )
            session.add(
                OutboxRecord(
                    event_id=event_id,
                    owner_id=owner_id,
                    event_type=envelope.event_type,
                    payload=envelope.json_bytes(),
                )
            )
    await session.flush()
    return created


__all__ = ["NotificationService", "queue_confirmed_broker_notifications"]
