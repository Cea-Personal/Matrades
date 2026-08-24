from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    OWNER = "OWNER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


@dataclass(frozen=True)
class Actor:
    actor_id: UUID
    owner_id: UUID
    role: Role
    step_up_verified: bool = False

    def require(self, *roles: Role, owner_id: UUID | None = None) -> None:
        if self.role not in roles or (owner_id is not None and owner_id != self.owner_id):
            raise PermissionError("operation is outside the actor scope")
