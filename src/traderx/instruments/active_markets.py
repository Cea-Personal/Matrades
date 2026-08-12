from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from traderx.identity.authorization import Actor, Role, require_role
from traderx.shared.types import ConcurrentModification


@dataclass(slots=True)
class ActiveAssignment:
    category: str
    instrument_id: UUID
    version: int
    approved_by: UUID | None = None
    active: bool = True


class ActiveMarketRegistry:
    """One explicit, human-approved market per constitutional category."""

    def __init__(self) -> None:
        self._assignments: dict[str, ActiveAssignment] = {}

    def activate(
        self,
        actor: Actor,
        *,
        category: str,
        instrument_id: UUID,
        expected_version: int | None,
        replace: bool,
    ) -> ActiveAssignment:
        require_role(actor, {Role.OWNER, Role.ADMIN}, "active-market.activate", require_mfa=True)
        current = self._assignments.get(category)
        if current and current.instrument_id != instrument_id and not replace:
            raise ConcurrentModification(
                "an active market can only change through explicit replacement"
            )
        if current and expected_version != current.version:
            raise ConcurrentModification("active market version is stale")
        assignment = ActiveAssignment(
            category, instrument_id, (current.version + 1) if current else 1, actor.id
        )
        self._assignments[category] = assignment
        return assignment

    def deactivate(self, actor: Actor, category: str, expected_version: int) -> None:
        require_role(actor, {Role.OWNER, Role.ADMIN}, "active-market.deactivate", require_mfa=True)
        current = self._assignments.get(category)
        if current is None or current.version != expected_version:
            raise ConcurrentModification("active market version is stale")
        current.active = False
