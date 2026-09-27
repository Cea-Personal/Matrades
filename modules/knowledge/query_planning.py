"""Deterministic, owner-scoped query planning for scheduled YouTube discovery."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.domain_types import AssetClass, InstrumentType
from packages.shared.store import ResourceRecord, ResourceStore

QueryMode = Literal["AUTO_MARKET", "FIXED"]
MAX_BASIS_AGE = timedelta(hours=72)
TOPICS = {
    "trend": "trend following strategy rules backtest",
    "pullback": "pullback entry confirmation strategy backtest",
    "momentum": "momentum trading strategy rules backtest",
    "breakout": "breakout trading strategy rules backtest",
    "mean_reversion": "mean reversion trading strategy rules backtest",
    "range": "range trading support resistance strategy backtest",
    "liquidity": "liquidity sweep reversal strategy rules backtest",
    "validation": "walk forward backtesting spread slippage strategy robustness",
}


class QueryCandidate(TypedDict):
    pair_key: str
    instrument: str
    asset_class: str
    instrument_type: str
    regime: str
    account_id: str
    market_research_run_id: str
    market_selection_id: str
    basis_observed_at: str
    score: float


def query_mode(schedule: dict[str, Any]) -> QueryMode:
    # Saved schedules predating automatic planning keep their explicit query.
    return "AUTO_MARKET" if schedule.get("query_mode") == "AUTO_MARKET" else "FIXED"


def _topics(regime: str) -> list[str]:
    tags = set(re.findall(r"[A-Z_]+", regime.upper()))
    if "RANGING" in tags:
        return ["mean_reversion", "range", "liquidity", "breakout", "validation"]
    if "TRENDING" in tags:
        return ["trend", "pullback", "momentum", "breakout", "validation"]
    return list(TOPICS)


def _regime_words(regime: str) -> str:
    tags = set(re.findall(r"[A-Z_]+", regime.upper()))
    return " ".join(
        words
        for tag, words in (
            ("TRENDING", "trending market"),
            ("RANGING", "range bound market"),
            ("HIGH_VOLATILITY", "high volatility"),
            ("LOW_VOLATILITY", "low volatility"),
        )
        if tag in tags
    )


def _instrument_words(instrument: str, asset_class: str) -> str:
    compact = instrument.upper().replace("/", "").replace("-", "")
    if asset_class == "METALS":
        for prefix, name in (("XAUUSD", "gold XAUUSD"), ("XAGUSD", "silver XAGUSD")):
            if compact.startswith(prefix):
                return name
    if asset_class == "FOREX":
        currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
        if compact[:3] in currencies and compact[3:6] in currencies:
            return f"{compact[:3]}/{compact[3:6]} forex"
    return f"{instrument} {asset_class.lower()}"


async def choose_scheduled_query(
    session: AsyncSession,
    owner_id: UUID,
    schedule: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One query per run: rotate pair coverage first, then regime-compatible topics.

    This does not call an LLM, a price provider, or SerpApi. All inputs are saved
    owner-scoped research. The chosen immutable plan is persisted on the run.
    """
    if query_mode(schedule) == "FIXED":
        return {
            "mode": "FIXED",
            "query": schedule.get("query", "trading strategy"),
            "reason": "Use the explicitly configured scheduled query.",
        }
    observed = now or datetime.now(UTC)
    store = ResourceStore(session)
    runs = list(
        (
            await session.scalars(
                select(ResourceRecord)
                .where(
                    ResourceRecord.kind == "research_run",
                    ResourceRecord.owner_id == owner_id,
                    ResourceRecord.state.in_(["COMPLETED", "DEGRADED"]),
                )
                .order_by(ResourceRecord.created_at.desc(), ResourceRecord.id.desc())
            )
        ).all()
    )
    latest: dict[str, ResourceRecord] = {}
    for run in runs:
        latest.setdefault(str(run.data.get("account_id")), run)
    accounts = {
        str(account.id)
        for account in await store.list("account", owner_id)
        if account.state == "ACTIVE"
    }
    current = {str(run.id): run for account, run in latest.items() if account in accounts}
    candidates: list[QueryCandidate] = []
    for selection in await store.list("market_selection", owner_id):
        current_run = current.get(str(selection.data.get("research_run_id")))
        if selection.state != "ACTIVE_MARKET_ANALYSIS" or current_run is None:
            continue
        candidate = selection.data.get("candidate", {})
        if not isinstance(candidate, dict):
            continue
        listing = candidate.get("listing", {})
        lane = candidate.get("lane", selection.data.get("lane", {}))
        fingerprint = candidate.get("fingerprint", {})
        if not all(isinstance(item, dict) for item in (listing, lane, fingerprint)):
            continue
        instrument = str(listing.get("symbol") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/._# -]{0,49}", instrument):
            continue
        try:
            basis_at = datetime.fromisoformat(str(fingerprint["observed_at"]))
            score = float(candidate.get("score", 0))
        except (KeyError, ValueError, TypeError):
            continue
        if (
            basis_at.tzinfo is None
            or basis_at > observed + timedelta(minutes=5)
            or observed - basis_at > MAX_BASIS_AGE
            or not math.isfinite(score)
            or not 0 <= score <= 100
        ):
            continue
        account_id = str(current_run.data["account_id"])
        if str(selection.data.get("account_id")) != account_id:
            continue
        asset_class = str(lane.get("asset_class") or "")
        instrument_type = str(lane.get("instrument_type") or "")
        if asset_class not in {item.value for item in AssetClass} or instrument_type not in {
            item.value for item in InstrumentType
        }:
            continue
        key = f"{account_id}:{asset_class}:{instrument_type}:{instrument}"
        candidates.append(
            {
                "pair_key": key,
                "instrument": instrument,
                "asset_class": asset_class,
                "instrument_type": instrument_type,
                "regime": str(fingerprint.get("regime", "UNCLASSIFIED")),
                "account_id": account_id,
                "market_research_run_id": str(current_run.id),
                "market_selection_id": str(selection.id),
                "basis_observed_at": basis_at.isoformat(),
                "score": score,
            }
        )
    history = [
        run.data.get("query_plan", {})
        for run in await store.list("youtube_discovery_run", owner_id)
        if run.data.get("trigger") == "SCHEDULED"
    ]
    candidates.sort(key=lambda item: (-item["score"], item["pair_key"]))
    # Keep the schedule bounded to the current top four; spread research across them.
    candidates = candidates[:4]
    if not candidates:
        topics = list(TOPICS)
        topic = min(
            topics,
            key=lambda name: sum(
                plan.get("basis") == "GENERAL_EDUCATION" and plan.get("topic") == name
                for plan in history
            ),
        )
        return {
            "mode": "AUTO_MARKET",
            "basis": "GENERAL_EDUCATION",
            "topic": topic,
            "query": f"trading {TOPICS[topic]}",
            "reason": (
                "No fresh selected pair is available; rotate general educational topics "
                "without claiming a current regime."
            ),
        }
    selected = min(
        candidates,
        key=lambda item: sum(plan.get("pair_key") == item["pair_key"] for plan in history),
    )
    topics = _topics(selected["regime"])
    topic = min(
        topics,
        key=lambda name: sum(
            plan.get("pair_key") == selected["pair_key"] and plan.get("topic") == name
            for plan in history
        ),
    )
    query = " ".join(
        filter(
            None,
            (
                _instrument_words(selected["instrument"], selected["asset_class"]),
                selected["instrument_type"],
                _regime_words(selected["regime"]),
                TOPICS[topic],
            ),
        )
    )
    return {
        **selected,
        "mode": "AUTO_MARKET",
        "basis": "LATEST_MARKET_RESEARCH",
        "topic": topic,
        "query": query[:240],
        "reason": (
            "Rotate among the latest top pairs, prioritizing least-searched pairs "
            "and regime-compatible topics."
        ),
    }
