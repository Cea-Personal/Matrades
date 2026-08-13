from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.shared.types import AuthenticationError, AuthorizationError, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

DatabaseSession = Annotated[Session, Depends(get_database_session)]


def _record_denial(
    database: Session,
    *,
    actor_type: str,
    action: str,
    reason: str,
    context: AuthenticationContext | None = None,
) -> None:
    database.add(
        AuditEvent.create(
            actor_type=actor_type,
            actor_id=context.user.id if context else None,
            actor_role=str(context.user.role) if context else None,
            action=action,
            outcome="DENIED",
            target_type="operational_api",
            target_id=None,
            target_version=None,
            reason=reason,
            assurance=context.session.assurance if context else None,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=None,
            previous_value=None,
            new_value=None,
            occurred_at=utc_now(),
        )
    )


def authenticated_operation_context(
    request: Request, database: DatabaseSession
) -> AuthenticationContext:
    """Require an MFA-backed browser session and retain rejected-access evidence."""

    try:
        return authenticated_context(request, database)
    except AuthenticationError as error:
        _record_denial(
            database,
            actor_type="ANONYMOUS",
            action="operational.read",
            reason=error.detail,
        )
        database.commit()
        raise


def operator_context(
    context: Annotated[AuthenticationContext, Depends(authenticated_operation_context)],
    database: DatabaseSession,
) -> AuthenticationContext:
    """Restrict ordinary product mutations to an MFA-assured owner or administrator."""

    actor = Actor(role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id)
    try:
        require_role(actor, {Role.OWNER, Role.ADMIN}, "operational.write", require_mfa=True)
    except AuthorizationError as error:
        _record_denial(
            database,
            actor_type="USER",
            action="operational.write",
            reason=error.detail,
            context=context,
        )
        database.commit()
        raise
    return context
