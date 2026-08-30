"""Account-scoped research matrix and lane result helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from modules.connections.models import ProviderBinding
from modules.research.models import ResearchLaneResult, TypedResearchRun
from packages.shared.domain_types import AssetClass, InstrumentType, LaneStatus, ResearchLaneKey

ALL_LANES = tuple(
    ResearchLaneKey(asset_class=asset_class, instrument_type=instrument_type)
    for asset_class in AssetClass
    for instrument_type in InstrumentType
)


def normalize_matrix(
    account_id: UUID,
    lanes: list[ResearchLaneKey] | None = None,
    *,
    version: int = 1,
    schedule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = lanes or list(ALL_LANES)
    keys = [lane.as_string() for lane in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("research matrix lanes must be unique")
    if not selected or len(selected) > 12:
        raise ValueError("research matrix must contain between one and twelve lanes")
    return {
        "account_id": str(account_id),
        "version": version,
        "lanes": [lane.model_dump(mode="json") for lane in selected],
        "schedule": schedule or {"enabled": True, "run_at": "00:00", "timezone": "UTC"},
    }


def aggregate_status(results: list[ResearchLaneResult]) -> str:
    if not results:
        return "RESEARCHING"
    terminal = {item.status for item in results}
    degraded = {LaneStatus.UNAVAILABLE, LaneStatus.STALE, LaneStatus.BLOCKED}
    if any(status in degraded for status in terminal):
        return "DEGRADED"
    complete = {LaneStatus.READY, LaneStatus.NO_TRADE, LaneStatus.NOT_CONFIGURED}
    if all(status in complete for status in terminal):
        return "COMPLETED"
    return "RESEARCHING"


def replace_lane(
    run: TypedResearchRun,
    lane: ResearchLaneKey,
    result: ResearchLaneResult,
) -> TypedResearchRun:
    if lane != result.lane:
        raise ValueError("replacement must remain in the same research lane")
    if lane.as_string() not in {item.as_string() for item in run.requested_lanes}:
        raise ValueError("replacement lane is not part of the run")
    results = [item for item in run.lane_results if item.lane != lane]
    results.append(result)
    return run.model_copy(update={"lane_results": results, "state": aggregate_status(results)})


def new_run(owner_id: UUID, account_id: UUID, matrix: dict[str, Any]) -> TypedResearchRun:
    lanes = [ResearchLaneKey.model_validate(item) for item in matrix["lanes"]]
    return TypedResearchRun(
        id=uuid4(),
        owner_id=owner_id,
        account_id=account_id,
        matrix_version=int(matrix.get("version", 1)),
        requested_lanes=lanes,
        created_at=datetime.now(UTC),
    )


def missing_binding(
    run_id: UUID, lane: ResearchLaneKey, bindings: list[ProviderBinding]
) -> ResearchLaneResult:
    return ResearchLaneResult(
        run_id=run_id,
        lane=lane,
        status=LaneStatus.NOT_CONFIGURED,
        reason_code="NO_VERIFIED_PROVIDER_BINDING",
        completed_at=datetime.now(UTC),
    )
