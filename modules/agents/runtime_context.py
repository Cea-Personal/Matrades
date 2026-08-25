"""Typed context validation at the agent runtime boundary."""

from __future__ import annotations

from typing import Any

from modules.agents.models import AgentDefinition


def validate_typed_context(agent: AgentDefinition, payload: dict[str, Any]) -> None:
    lane = payload.get("lane")
    if not agent.required_lanes:
        return
    if not isinstance(lane, dict):
        raise ValueError("typed agent invocation requires a lane envelope")
    lane_key = f"{lane.get('asset_class')}:{lane.get('instrument_type')}"
    allowed = {item.as_string() for item in agent.required_lanes}
    if lane_key not in allowed:
        raise ValueError("agent invocation lane is outside the configured capability")
    if not payload.get("source_cut_refs") and not payload.get("evidence_refs"):
        raise ValueError("typed agent invocation requires source-cut evidence references")
