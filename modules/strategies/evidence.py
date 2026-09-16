"""Immutable, owner-scoped evidence preparation for strategy research."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from modules.backtesting.engine import BacktestCandle
from modules.research.models import MarketFingerprint, ResearchCandidate
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit


class ApprovedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    instrument: str
    category: str
    score: float
    fingerprint: MarketFingerprint
    evidence: list[str] = Field(default_factory=list)
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: str | None = None
    specification_version_id: str | None = None
    quantity_unit: QuantityUnit | None = None
    futures_contract_id: str | None = None


class EvidenceReference(BaseModel):
    id: str
    kind: str
    summary: str
    source_id: str | None = None
    source_version: str | None = None
    observed_at: AwareDatetime | None = None
    authority: str = "AUTHORITATIVE"


class StrategyEvidencePack(BaseModel):
    """Agent-visible discovery evidence. The holdout is deliberately not a field."""

    selection_id: str
    research_run_id: str
    account_id: str
    instrument: str
    category: str
    collected_at: AwareDatetime
    market_fingerprint: dict[str, Any]
    historical_discovery: dict[str, Any]
    account_context: dict[str, Any]
    policy_context: list[dict[str, Any]] = Field(default_factory=list)
    prior_strategy_context: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_context: list[dict[str, Any]] = Field(default_factory=list)
    references: list[EvidenceReference]
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    quantity_unit: QuantityUnit | None = None
    venue_instrument_id: str | None = None
    futures_contract_id: str | None = None
    specification_version_id: str | None = None
    source_cut_refs: list[str] = Field(default_factory=list)


def resolve_approved_candidate(
    selection: dict[str, Any],
    research_run: dict[str, Any],
    *,
    now: datetime,
    max_age: timedelta,
) -> ApprovedCandidate:
    typed = selection.get("candidate")
    if isinstance(typed, dict) and selection.get("state") == "ACTIVE_MARKET_ANALYSIS":
        lane = dict(typed.get("lane", selection.get("lane", {})))
        listing = dict(typed.get("listing", {}))
        fingerprint = dict(typed.get("fingerprint", {}))
        observed_at = datetime.fromisoformat(str(fingerprint["observed_at"]))
        if now.tzinfo is None or observed_at.tzinfo is None:
            raise ValueError("freshness evaluation requires aware timestamps")
        if observed_at > now + timedelta(minutes=5):
            raise ValueError("typed market fingerprint is future-dated")
        if now - observed_at > max_age:
            raise ValueError("typed market fingerprint is stale; rerun market research")
        category = {
            "FOREX": "FOREX",
            "METALS": "METAL",
            "CRYPTOCURRENCY": "CRYPTO",
            "STOCKS": "FOREX",
        }[str(lane["asset_class"])]
        market_fingerprint = MarketFingerprint(
            instrument=str(listing["symbol"]),
            category=category,
            observed_at=observed_at,
            source=str(listing.get("provider", "typed_provider")),
            source_version=str(fingerprint.get("source_cut_id", "typed-source-cut")),
            regime=str(fingerprint.get("regime", "UNCLASSIFIED")),
            trend_score=float(fingerprint.get("trend_score", 0)),
            volatility_score=float(fingerprint.get("volatility_score", 0)),
            liquidity_score=float(fingerprint.get("liquidity_score", 0)),
            spread_score=0.0,
            fundamental_score=None,
            sentiment_score=None,
            event_risk=None,
            positioning_score=None,
            correlation_risk=None,
            data_quality=float(fingerprint.get("data_quality", 0)),
        )
        specification = dict(typed.get("specification", {}))
        return ApprovedCandidate(
            account_id=str(selection["account_id"]),
            instrument=str(listing["symbol"]),
            category=category,
            score=float(typed.get("score", 0)),
            fingerprint=market_fingerprint,
            evidence=[str(item) for item in typed.get("evidence", [])],
            asset_class=lane.get("asset_class"),
            instrument_type=lane.get("instrument_type"),
            venue_instrument_id=str(listing.get("id")) if listing.get("id") else None,
            specification_version_id=(
                str(specification.get("id")) if specification.get("id") else None
            ),
            quantity_unit=specification.get("quantity_unit"),
            futures_contract_id=listing.get("futures_contract_id"),
        )
    if selection.get("action") == "NO_TRADE" or not selection.get("selected"):
        raise ValueError("an approved market selection with at least one instrument is required")
    selected = {
        str(category): str(instrument).upper()
        for category, instrument in dict(selection["selected"]).items()
    }
    matching: list[ResearchCandidate] = []
    for raw in research_run.get("candidates", []):
        candidate = ResearchCandidate.model_validate(raw)
        if selected.get(candidate.category.value) == candidate.instrument.upper():
            matching.append(candidate)
    if not matching:
        raise ValueError("approved candidate evidence is unavailable; rerun market research")
    candidate = sorted(matching, key=lambda item: (-item.score, item.instrument))[0]
    observed_at = candidate.fingerprint.observed_at
    if now.tzinfo is None:
        raise ValueError("freshness evaluation requires an aware timestamp")
    if observed_at > now + timedelta(minutes=5):
        raise ValueError("approved market fingerprint is future-dated")
    if now - observed_at > max_age:
        raise ValueError("approved market fingerprint is stale; rerun market research")
    return ApprovedCandidate(
        account_id=str(research_run["account_id"]),
        instrument=candidate.instrument,
        category=candidate.category.value,
        score=candidate.score,
        fingerprint=candidate.fingerprint,
        evidence=candidate.evidence + candidate.agent_evidence,
    )


def split_research_history(
    candles: list[BacktestCandle], *, discovery_ratio: Decimal = Decimal("0.70")
) -> tuple[list[BacktestCandle], list[BacktestCandle]]:
    if not Decimal("0.5") <= discovery_ratio <= Decimal("0.9"):
        raise ValueError("discovery ratio must be between 0.5 and 0.9")
    chronological = sorted(candles, key=lambda item: item.observed_at)
    if chronological != candles:
        raise ValueError("historical evidence must be chronological")
    if len(candles) < 12:
        raise ValueError("at least twelve candles are required for discovery and holdout")
    split_at = int(Decimal(len(candles)) * discovery_ratio)
    split_at = max(6, min(split_at, len(candles) - 6))
    return candles[:split_at], candles[split_at:]


def candle_checksum(candles: list[BacktestCandle]) -> str:
    canonical = json.dumps(
        [item.model_dump(mode="json") for item in candles], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def historical_summary(candles: list[BacktestCandle]) -> dict[str, str | int]:
    if not candles:
        raise ValueError("historical summary requires candles")
    closes = [item.close for item in candles]
    returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1]
        for index in range(1, len(closes))
        if closes[index - 1] != 0
    ]
    mean = sum(returns, Decimal("0")) / Decimal(len(returns)) if returns else Decimal("0")
    variance = (
        sum(((item - mean) ** 2 for item in returns), Decimal("0")) / Decimal(len(returns))
        if returns
        else Decimal("0")
    )
    return {
        "candle_count": len(candles),
        "start_at": candles[0].observed_at.isoformat(),
        "end_at": candles[-1].observed_at.isoformat(),
        "first_close": str(closes[0]),
        "last_close": str(closes[-1]),
        "return": str((closes[-1] - closes[0]) / closes[0]) if closes[0] else "0",
        "mean_bar_return": str(mean),
        "return_variance": str(variance),
        "average_range": str(
            sum((item.high - item.low for item in candles), Decimal("0")) / Decimal(len(candles))
        ),
    }


def lexical_knowledge_context(
    sources: list[Any], query: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Retrieve only owner-preselected records; callers enforce owner scope in the query."""
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    hits: list[dict[str, Any]] = []
    for source in sources:
        if source.state != "ACTIVE":
            continue
        for segment in source.data.get("segments", []):
            terms = set(re.findall(r"[a-z0-9]+", str(segment.get("text", "")).lower()))
            overlap = len(query_terms & terms)
            if not overlap:
                continue
            hits.append(
                {
                    "reference_id": f"knowledge:{segment['id']}",
                    "source_id": str(source.id),
                    "source_name": source.data.get("name"),
                    "source_version": str(source.version),
                    "segment_id": segment["id"],
                    "score": overlap / max(len(query_terms), 1),
                    "text": str(segment.get("text", ""))[:1200],
                    "authority": "CONTEXT_ONLY",
                }
            )
    hits.sort(key=lambda item: (-item["score"], str(item["source_name"]), item["segment_id"]))
    return hits[:limit]
