from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.authorization import Actor, Role
from modules.identity.persistence import AuthTokenRecord, SessionRecord
from packages.shared.database import session_factory
from packages.shared.domain_types import utc_now


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def current_actor(
    db: Annotated[AsyncSession, Depends(get_db)],
    matrades_session: Annotated[str | None, Cookie()] = None,
) -> Actor:
    if not matrades_session:
        raise HTTPException(status_code=401, detail="authenticated session required")
    digest = hashlib.sha256(matrades_session.encode()).hexdigest()
    session = await db.scalar(
        select(SessionRecord).where(
            SessionRecord.token_hash == digest,
            SessionRecord.revoked_at.is_(None),
            SessionRecord.expires_at > utc_now(),
        )
    )
    if session is None:
        raise HTTPException(status_code=401, detail="session expired or revoked")
    try:
        step_up = session.step_up_at is not None and (
            utc_now() - session.step_up_at < timedelta(minutes=10)
        )
        return Actor(session.user_id, session.owner_id, Role(session.role), step_up)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid actor context") from exc


def require_roles(*roles: Role):
    async def dependency(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient role")
        return actor

    return dependency


def require_step_up(scope: str):
    async def dependency(
        actor: Annotated[Actor, Depends(current_actor)],
        db: Annotated[AsyncSession, Depends(get_db)],
        step_up_grant: Annotated[str | None, Header(alias="Step-Up-Grant")] = None,
    ) -> Actor:
        if actor.step_up_verified:
            return actor
        if not step_up_grant:
            raise HTTPException(status_code=403, detail="recent MFA step-up required")
        digest = hashlib.sha256(step_up_grant.encode()).hexdigest()
        grant = await db.scalar(
            select(AuthTokenRecord).where(
                AuthTokenRecord.token_hash == digest,
                AuthTokenRecord.user_id == actor.actor_id,
                AuthTokenRecord.kind == "STEP_UP",
                AuthTokenRecord.used_at.is_(None),
                AuthTokenRecord.expires_at > utc_now(),
            )
        )
        if grant is None or grant.payload.get("scope") not in {scope, "*"}:
            raise HTTPException(status_code=403, detail="invalid step-up grant")
        grant.used_at = utc_now()
        return Actor(actor.actor_id, actor.owner_id, actor.role, True)

    return dependency
