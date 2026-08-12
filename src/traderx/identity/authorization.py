from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from traderx.shared.types import AuthorizationError


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


@dataclass(frozen=True, slots=True)
class Actor:
    role: Role
    assurance: str
    id: UUID | None = None


def require_role(
    actor: Actor, allowed: Iterable[Role], action: str, *, require_mfa: bool = False
) -> None:
    if actor.role not in set(allowed):
        raise AuthorizationError(f"{actor.role} is not permitted to perform {action}")
    if require_mfa and actor.assurance != "MFA":
        raise AuthorizationError(f"{action} requires recent multi-factor authentication")
