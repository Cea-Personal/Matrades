from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    purpose: str
    inputs: dict[str, object]
    parameters: dict[str, object]


def manifest_for(request: ResearchRequest) -> str:
    body = json.dumps(
        {"purpose": request.purpose, "inputs": request.inputs, "parameters": request.parameters},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def summarize(outcomes: list[dict[str, object]]) -> dict[str, object]:
    accepted = sum(1 for item in outcomes if item.get("outcome") == "ACCEPTED")
    return {"total": len(outcomes), "accepted": accepted, "rejected": len(outcomes) - accepted}
