"""Read-only research archive and generated-code explorer for the Extras UI."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db
from modules.identity.authorization import Actor
from modules.research.artifacts import ResearchCycleArchive
from modules.strategies.compiler import compile_strategy
from packages.shared.config import get_settings
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification

router = APIRouter(prefix="/extras", tags=["Extras"])

FOLDERS: tuple[dict[str, str], ...] = (
    {
        "id": "market-research",
        "label": "Market research",
        "description": "Autonomous Forex, metals, and crypto cycles with ranked evidence.",
    },
    {
        "id": "strategy-research",
        "label": "Strategy research",
        "description": (
            "AI-generated and AI-assisted strategy hypotheses, evidence, and validation."
        ),
    },
    {
        "id": "trade-recommendations",
        "label": "Trade recommendations",
        "description": "HIL-2 ideas, risk evidence, HIL-3 monitoring recommendations, and reasons.",
    },
    {
        "id": "generated-code",
        "label": "Generated code",
        "description": (
            "Deterministic strategy evaluator source generated from approved specifications."
        ),
    },
    {
        "id": "mt5-bridge-ea",
        "label": "MT5 bridge EA",
        "description": "The read-only MQL5 Expert Advisor used to publish signed MT5 snapshots.",
    },
)

EA_PATH = Path(__file__).resolve().parents[4] / "bridges" / "mt5" / "MatradesMT5BridgeEA.mq5"


def _artifact_details(
    record: ResourceRecord, manifests: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    artifact = record.data.get("artifact") or record.data.get("research_artifact")
    if not isinstance(artifact, dict):
        return None
    path = artifact.get("relative_path")
    return manifests.get(str(path)) if path else None


def _cycle_item(
    record: ResourceRecord, cycle_type: str, manifests: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    manifest = _artifact_details(record, manifests)
    details = manifest.get("details", {}) if manifest else {}
    # Resource state/data is authoritative for current state; the immutable
    # manifest is included as the historical evidence used by the cycle.
    return {
        "id": str(record.id),
        "folder": "market-research" if cycle_type == "market_research" else "strategy-research",
        "cycle_type": cycle_type,
        "state": record.state,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "completed_at": record.data.get("completed_at"),
        "account_id": record.data.get("account_id"),
        "trigger": record.data.get("trigger"),
        "summary": {
            "instrument": record.data.get("instrument")
            or record.data.get("research_basis", {}).get("instrument"),
            "category": record.data.get("category")
            or record.data.get("research_basis", {}).get("category"),
            "candidate_count": len(record.data.get("candidates", [])),
            "selected_hypothesis_id": record.data.get("selected_hypothesis_id"),
            "origin": record.data.get("origin"),
            "reason": record.data.get("rationale")
            or record.data.get("failure")
            or record.data.get("degraded_reasons"),
        },
        "artifact": record.data.get("artifact") or record.data.get("research_artifact"),
        "details": details or record.data,
    }


def _trade_item(record: ResourceRecord) -> dict[str, Any]:
    data = record.data
    risk_value = data.get("risk")
    risk = risk_value if isinstance(risk_value, dict) else {}
    return {
        "id": str(record.id),
        "folder": "trade-recommendations",
        "kind": record.kind,
        "state": record.state,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "instrument": data.get("instrument"),
        "direction": data.get("direction"),
        "action": data.get("action"),
        "reason": data.get("reason") or data.get("critic_result") or data.get("decision_reason"),
        "why": {
            "evidence": data.get("evidence", []),
            "critic_result": data.get("critic_result"),
            "risk_decision": risk.get("decision"),
            "risk_snapshot": risk.get("snapshot"),
            "facts": data.get("facts"),
            "invalidation": data.get("invalidation"),
        },
        "details": data,
    }


def _generated_code(record: ResourceRecord) -> dict[str, Any]:
    specification = record.data.get("specification") or record.data.get("proposed_specification")
    code = record.data.get("generated_code")
    if not code and isinstance(specification, dict):
        try:
            code = compile_strategy(
                StrategySpecification.model_validate(specification)
            ).generated_code
        except (TypeError, ValueError):
            code = None
    return {
        "id": str(record.id),
        "folder": "generated-code",
        "kind": record.kind,
        "name": (specification or {}).get("name")
        if isinstance(specification, dict)
        else record.data.get("name"),
        "strategy_version": record.data.get("strategy_version"),
        "language": record.data.get("generated_code_language", "python"),
        "artifact_hash": record.data.get("artifact_hash") or record.data.get("fingerprint"),
        "state": record.state,
        "updated_at": record.updated_at,
        "code": code,
        "specification": specification,
    }


def _mt5_ea() -> dict[str, Any]:
    if not EA_PATH.is_file():
        raise FileNotFoundError(EA_PATH)
    content = EA_PATH.read_text(encoding="utf-8")
    return {
        "id": "matrades-mt5-bridge-ea",
        "folder": "mt5-bridge-ea",
        "kind": "mt5_bridge_ea",
        "name": "MatradesMT5BridgeEA.mq5",
        "language": "mql5",
        "state": "AVAILABLE",
        "updated_at": EA_PATH.stat().st_mtime,
        "artifact_hash": hashlib.sha256(content.encode()).hexdigest(),
        "download_path": "/api/v1/extras/mt5-ea/download",
        "code": content,
    }


async def _build_overview(actor: Actor, db: AsyncSession) -> dict[str, Any]:
    store = ResourceStore(db)
    archive = ResearchCycleArchive(get_settings().research_artifact_root)

    def manifest_map(records: list[ResourceRecord]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for record in records:
            artifact = record.data.get("artifact") or record.data.get("research_artifact")
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("relative_path")
            if path:
                try:
                    result[str(path)] = archive.read_manifest(
                        owner_id=actor.owner_id, relative_path=str(path)
                    )
                except (FileNotFoundError, OSError, ValueError):
                    continue
        return result

    market = await store.list("research_run", actor.owner_id)
    strategy = [
        *await store.list("strategy_research_run", actor.owner_id),
        *await store.list("strategy_backtest", actor.owner_id),
    ]
    market_manifests = manifest_map(market)
    strategy_manifests = manifest_map(strategy)
    trades = [
        *await store.list("trade_proposal", actor.owner_id),
        *await store.list("management_recommendation", actor.owner_id),
    ]
    versions = await store.list("strategy_version", actor.owner_id)
    drafts = await store.list("strategy_draft", actor.owner_id)
    code_records = [*versions, *drafts]
    folders = [
        {
            **folder,
            "count": {
                "market-research": len(market),
                "strategy-research": len(strategy),
                "trade-recommendations": len(trades),
                "generated-code": len(code_records),
                "mt5-bridge-ea": 1 if EA_PATH.is_file() else 0,
            }[folder["id"]],
        }
        for folder in FOLDERS
    ]
    return {
        "folders": folders,
        "items": {
            "market-research": [
                _cycle_item(item, "market_research", market_manifests) for item in market
            ],
            "strategy-research": [
                _cycle_item(
                    item,
                    "strategy_research"
                    if item.kind == "strategy_research_run"
                    else "strategy_backtest",
                    strategy_manifests,
                )
                for item in strategy
            ],
            "trade-recommendations": [_trade_item(item) for item in trades],
            "generated-code": [_generated_code(item) for item in code_records],
            "mt5-bridge-ea": [_mt5_ea()] if EA_PATH.is_file() else [],
        },
    }


@router.get("")
@router.get("/overview")
async def extras_overview(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    return await _build_overview(actor, db)


@router.get("/cycles")
async def list_cycles(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    folder: str | None = None,
) -> list[dict[str, Any]]:
    overview = await _build_overview(actor, db)
    if folder and folder not in overview["items"]:
        raise HTTPException(404, "Extras folder not found")
    return overview["items"].get(folder or "market-research", [])


@router.get("/cycles/{cycle_id}")
async def get_cycle(
    cycle_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    overview = await _build_overview(actor, db)
    for items in overview["items"].values():
        for item in items:
            if item.get("id") == str(cycle_id):
                return item
    raise HTTPException(404, "research cycle not found")


@router.get("/generated-code")
async def list_generated_code(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    overview = await _build_overview(actor, db)
    return overview["items"]["generated-code"]


@router.get("/generated-code/{strategy_id}")
async def get_generated_code(
    strategy_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    record = await ResourceStore(db).get("strategy_version", strategy_id, actor.owner_id)
    if record is None:
        raise HTTPException(404, "strategy version not found")
    return _generated_code(record)


@router.get("/mt5-ea")
async def get_mt5_ea(_: Annotated[Actor, Depends(current_actor)]) -> dict[str, Any]:
    try:
        return _mt5_ea()
    except FileNotFoundError as exc:
        raise HTTPException(404, "MT5 bridge EA source is not installed") from exc


@router.get("/mt5-ea/download")
async def download_mt5_ea(_: Annotated[Actor, Depends(current_actor)]) -> FileResponse:
    if not EA_PATH.is_file():
        raise HTTPException(404, "MT5 bridge EA source is not installed")
    return FileResponse(
        EA_PATH,
        media_type="text/plain",
        filename="MatradesMT5BridgeEA.mq5",
    )
