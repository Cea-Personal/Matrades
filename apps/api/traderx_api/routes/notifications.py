from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.notifications.model import (
    NotificationEvent,
    NotificationPreference,
    RoutedNotification,
)
from traderx.shared.types import InvalidTransition, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class PreferenceCommand(BaseModel):
    channel: Literal["WEB", "EMAIL", "TELEGRAM"]
    minimum_severity: Literal["INFO", "ACTION", "WARNING", "HIGH", "CRITICAL"]
    enabled: bool


@router.get("/inbox")
def inbox(context: Viewer, database: DatabaseSession) -> dict[str, object]:
    routes = database.scalars(
        select(RoutedNotification)
        .where(RoutedNotification.user_id == context.user.id, RoutedNotification.channel == "WEB")
        .order_by(RoutedNotification.created_at.desc())
    ).all()
    items = []
    for routed in routes:
        event = database.get(NotificationEvent, routed.event_id)
        if event:
            items.append(
                {
                    "id": str(routed.id),
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "payload": event.payload,
                    "state": routed.state,
                    "read_at": routed.read_at.isoformat() if routed.read_at else None,
                    "created_at": event.created_at.isoformat(),
                }
            )
    return {"items": items, "durable_critical_inbox": True}


@router.post("/inbox/{notification_id}/read")
def mark_read(
    notification_id: UUID, context: Operator, database: DatabaseSession
) -> dict[str, object]:
    routed = database.get(RoutedNotification, notification_id)
    if routed is None or routed.user_id != context.user.id:
        raise InvalidTransition("the requested notification does not exist")
    routed.read_at = utc_now()
    routed.state = "READ"
    database.commit()
    return {"id": str(routed.id), "state": routed.state, "read_at": routed.read_at.isoformat()}


@router.get("/preferences")
def preferences(context: Viewer, database: DatabaseSession) -> dict[str, object]:
    items = database.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == context.user.id)
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "channel": item.channel,
                "minimum_severity": item.minimum_severity,
                "enabled": item.enabled,
            }
            for item in items
        ]
    }


@router.put("/preferences/{channel}")
def set_preference(
    channel: str, payload: PreferenceCommand, context: Operator, database: DatabaseSession
) -> dict[str, object]:
    if channel.upper() != payload.channel:
        raise InvalidTransition("notification channel does not match the request path")
    preference = database.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == context.user.id,
            NotificationPreference.channel == payload.channel,
        )
    )
    if preference is None:
        preference = NotificationPreference(
            user_id=context.user.id,
            channel=payload.channel,
            minimum_severity=payload.minimum_severity,
            enabled=payload.enabled,
        )
        database.add(preference)
    else:
        preference.minimum_severity = payload.minimum_severity
        preference.enabled = payload.enabled
    database.commit()
    database.refresh(preference)
    return {
        "id": str(preference.id),
        "channel": preference.channel,
        "minimum_severity": preference.minimum_severity,
        "enabled": preference.enabled,
    }


@router.post("/channels/{channel}/test", status_code=202)
def test_channel(
    channel: Literal["WEB", "EMAIL", "TELEGRAM"], context: Operator, database: DatabaseSession
) -> dict[str, object]:
    now = utc_now()
    event = NotificationEvent(
        event_type="NOTIFICATION_CHANNEL_TEST",
        severity="INFO",
        dedupe_key=f"channel-test:{context.user.id}:{channel}:{now.isoformat()}",
        payload={
            "title": f"{channel.title()} channel test",
            "message": "TraderX notification test completed.",
            "user_id": str(context.user.id),
        },
        created_at=now,
    )
    database.add(event)
    database.flush()
    database.add(
        RoutedNotification(
            event_id=event.id,
            user_id=context.user.id,
            channel="WEB",
            state="DELIVERED",
            read_at=None,
        )
    )
    if channel != "WEB":
        database.add(
            RoutedNotification(
                event_id=event.id,
                user_id=context.user.id,
                channel=channel,
                state="PENDING",
                read_at=None,
            )
        )
    database.commit()
    return {
        "event_id": str(event.id),
        "channel": channel,
        "state": "DELIVERED" if channel == "WEB" else "QUEUED",
        "web_inbox_copy": True,
    }
