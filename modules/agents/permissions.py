from __future__ import annotations

from dataclasses import dataclass

PROHIBITED = {
    "broker.write",
    "order.create",
    "position.modify",
    "policy.hard.write",
    "guardrail.reduce",
    "credential.read_raw",
    "strategy.activate",
}


@dataclass(frozen=True)
class PermissionSet:
    version: str
    tools: tuple[str, ...]

    def __post_init__(self) -> None:
        denied = PROHIBITED.intersection(self.tools)
        if denied:
            raise ValueError(f"prohibited agent tools: {sorted(denied)}")


def authority_unchanged(before: PermissionSet, after: PermissionSet) -> bool:
    return before == after
