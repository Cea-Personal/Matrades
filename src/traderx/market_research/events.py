from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from traderx.shared.events import append_outbox, event_envelope

SCHEDULE_CHANGED = "com.traderx.markets.research-schedule-updated.v1"
OCCURRENCE_CLAIMED = "com.traderx.markets.research-occurrence-started.v1"
OCCURRENCE_OVERLAP_SKIPPED = "com.traderx.markets.research-occurrence-skipped.v1"
COORDINATED_COMPLETED = "com.traderx.markets.coordinated-research-completed.v1"
CATEGORY_BLOCKED = "com.traderx.markets.category-research-blocked.v1"
SOURCE_FALLBACK_SELECTED = "com.traderx.markets.source-fallback-applied.v1"
MODEL_CONFIGURATION_CHANGED = "com.traderx.markets.model-selection-changed.v1"
LLM_ANALYSIS_COMPLETED = "com.traderx.markets.llm-analysis-completed.v1"
LLM_ANALYSIS_UNAVAILABLE = "com.traderx.markets.llm-analysis-unavailable.v1"
LLM_ANALYSIS_RETRY_REQUESTED = "com.traderx.markets.llm-analysis-retry-requested.v1"


def emit_market_research_fact(
    database: Session,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    aggregate_version: int,
    event_type: str,
    data: dict[str, object],
    now: datetime,
    correlation_id: str,
    actor_id: UUID | None = None,
) -> None:
    append_outbox(
        database,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        envelope=event_envelope(
            source="traderx.market-research",
            event_type=event_type,
            subject=f"{aggregate_type}/{aggregate_id}",
            data=data,
            now=now,
            correlation_id=correlation_id,
            actor_id=actor_id,
            aggregate_version=aggregate_version,
        ),
    )
