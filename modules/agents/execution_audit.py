from __future__ import annotations

from modules.agents.models import AgentExecution


class ExecutionAudit:
    def __init__(self) -> None:
        self._items: list[AgentExecution] = []

    def record(self, execution: AgentExecution) -> None:
        if execution.selected_runtime != execution.actual_runtime:
            raise ValueError("cross-runtime execution is forbidden")
        self._items.append(execution)

    def all(self) -> tuple[AgentExecution, ...]:
        return tuple(self._items)
