from __future__ import annotations

from datetime import UTC, timedelta
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from traderx.market_data.model import Instrument
from traderx.market_research.service import execute_market_research, refresh_mt5_instrument_catalog
from traderx.shared.types import utc_now
from traderx.strategies.model import Strategy, StrategyVersion
from traderx.strategies.staleness import classify_evidence
from traderx.validation.model import ValidationRun
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.market_rotation.research", bind=True, acks_late=True)
def replacement_research(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    run_ids: list[str] = []
    with session_factory().begin() as database:
        imported = refresh_mt5_instrument_catalog(database)
        for category in ("COMMODITY", "FOREX", "CRYPTO"):
            run = execute_market_research(
                database,
                category=category,
                method_version="market-suitability-v1",
            )
            run_ids.append(str(run.id))
    return {
        "status": "COMPLETED",
        "catalog_imported": str(imported),
        "research_run_ids": ",".join(run_ids),
        "automatic_replacement": "false",
    }


@shared_task(name="traderx.market_rotation.revalidation_plan", bind=True, acks_late=True)
def revalidation_plan(self, instrument_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    try:
        resolved_instrument_id = UUID(instrument_id)
    except ValueError:
        return {"instrument_id": instrument_id, "status": "INVALID_INSTRUMENT_ID"}
    with session_factory().begin() as database:
        refresh_mt5_instrument_catalog(database)
        instrument = database.get(Instrument, resolved_instrument_id)
        if instrument is None:
            return {"instrument_id": instrument_id, "status": "INSTRUMENT_NOT_FOUND"}

        version_ids = list(
            database.scalars(
                select(StrategyVersion.id)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(Strategy.instrument_id == instrument.id)
            )
        )
        latest_validation = (
            database.scalar(
                select(ValidationRun)
                .where(ValidationRun.strategy_version_id.in_(version_ids))
                .order_by(ValidationRun.created_at.desc())
                .limit(1)
            )
            if version_ids
            else None
        )
        now = utc_now()
        validated_at = (
            latest_validation.created_at if latest_validation else now - timedelta(days=365)
        )
        if validated_at.tzinfo is None:
            validated_at = validated_at.replace(tzinfo=UTC)
        closes = instrument.contract_spec.get("closes")
        plan = classify_evidence(
            validated_at=validated_at,
            now=now,
            data_gap=not isinstance(closes, list) or len(closes) < 30,
        )
    return {
        "instrument_id": instrument_id,
        "status": "PLAN_COMPLETED",
        "freshness": plan.freshness,
        "steps": ",".join(plan.steps),
        "automatic_reactivation": "false",
    }
