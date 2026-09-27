from __future__ import annotations

from typing import Any


class RuntimeResult(dict[str, Any]):
    """Out-of-band adapter evidence, never keys in an agent's output schema."""

    def __init__(
        self,
        data: dict[str, Any],
        *,
        actual_model: str | None = None,
        model_evidence_source: str | None = None,
        orchestrator_model: str | None = None,
    ) -> None:
        super().__init__(data)
        self.actual_model = actual_model
        self.model_evidence_source = model_evidence_source
        self.orchestrator_model = orchestrator_model
