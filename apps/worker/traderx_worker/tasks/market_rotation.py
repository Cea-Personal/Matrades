from __future__ import annotations

from datetime import UTC, timedelta
from typing import cast
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from traderx.market_data.model import Instrument
from traderx.market_research.coordinator import create_coordinated_run
from traderx.market_research.model import (
    CoordinatedMarketResearchRun,
    MarketResearchModelConfiguration,
    MarketResearchRun,
    MarketResearchSchedule,
)
from traderx.market_research.scheduling import claim_occurrence
from traderx.market_research.service import refresh_mt5_instrument_catalog
from traderx.shared.types import utc_now
from traderx.strategies.model import Strategy, StrategyVersion
from traderx.strategies.staleness import classify_evidence
from traderx.validation.model import ValidationRun
from traderx_worker.tasks.database import session_factory
from traderx_worker.tasks.market_research import (
    dispatch_coordinated_run,
    retry_pinned_analysis,
)


@shared_task(name="traderx.market_rotation.scan_due", bind=True, acks_late=True)
def scan_due_schedules(self) -> dict[str, object]:  # type: ignore[no-untyped-def]
    now = utc_now()
    dispatch_ids: list[str] = []
    analysis_retry_ids: list[str] = []
    overlaps = 0
    with session_factory().begin() as database:
        schedules = list(
            database.scalars(
                select(MarketResearchSchedule).where(
                    MarketResearchSchedule.enabled.is_(True),
                    MarketResearchSchedule.next_run_at <= now,
                )
            )
        )
        for schedule in schedules:
            active = database.scalar(
                select(CoordinatedMarketResearchRun).where(
                    CoordinatedMarketResearchRun.account_id == schedule.account_id,
                    CoordinatedMarketResearchRun.state.in_(["QUEUED", "RUNNING"]),
                )
            )
            occurrence = claim_occurrence(
                database,
                schedule,
                scheduled_for=schedule.next_run_at,
                claimed_at=now,
                active_run_id=active.id if active else None,
                lease_owner="celery-due-scanner",
                lease_token=f"schedule-{schedule.id}-{now.isoformat()}",
            )
            if active is not None:
                overlaps += 1
                continue
            model = database.scalar(
                select(MarketResearchModelConfiguration).where(
                    MarketResearchModelConfiguration.scope == "GLOBAL"
                )
            )
            pin = (
                {
                    "llm_integration_id": model.llm_integration_id,
                    "provider_key": model.provider_key,
                    "exact_model_id": model.exact_model_id,
                    "catalogue_revision": model.catalogue_revision,
                    "adapter_revision": model.adapter_revision,
                    "prompt_template_version": model.prompt_template_version,
                    "output_schema_version": model.output_schema_version,
                    "inference_policy_version": model.inference_policy_version,
                }
                if model
                else None
            )
            parent = create_coordinated_run(
                database,
                account_id=schedule.account_id,
                trigger="SCHEDULED",
                methodology_version="market-suitability-v2",
                source_catalogue_revision="2026-08-14.v1",
                freshness_policy_manifest={"default": "freshness-2026-08-v1"},
                retry_policy_manifest={"default": "retry-2026-08-v1"},
                now=now,
                llm_pin=pin,
                occurrence=occurrence,
            )
            dispatch_ids.append(str(parent.id))
        # Manual parents are also durable database commands. The browser/API does not
        # own their lifetime; the same worker wake-up recovers any queued parent.
        for parent in database.scalars(
            select(CoordinatedMarketResearchRun).where(
                CoordinatedMarketResearchRun.state.in_(["QUEUED", "RUNNING"])
            )
        ):
            unfinished = database.scalar(
                select(MarketResearchRun.id)
                .where(
                    MarketResearchRun.coordinated_run_id == parent.id,
                    MarketResearchRun.state.in_(["QUEUED", "RUNNING"]),
                )
                .limit(1)
            )
            if unfinished is None:
                continue
            value = str(parent.id)
            if value not in dispatch_ids:
                dispatch_ids.append(value)
        analysis_retry_ids = [
            str(run_id)
            for run_id in database.scalars(
                select(MarketResearchRun.id).where(
                    MarketResearchRun.llm_analysis_state == "RETRY_QUEUED"
                )
            )
        ]
    for run_id in dispatch_ids:
        dispatch_coordinated_run.delay(run_id)
    for run_id in analysis_retry_ids:
        retry_pinned_analysis.delay(run_id)
    return {
        "status": "SCANNED",
        "dispatched": dispatch_ids,
        "analysis_retries": analysis_retry_ids,
        "overlaps": overlaps,
    }


@shared_task(name="traderx.market_rotation.research", bind=True, acks_late=True)
def replacement_research(self) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Compatibility alias; database schedule remains the only timing authority."""

    return cast(dict[str, object], scan_due_schedules.run())


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
