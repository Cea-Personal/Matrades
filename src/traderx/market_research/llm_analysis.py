from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traderx.integrations.ports import LlmAnalysisPort, LlmAnalysisRequest, LlmAnalysisResponse
from traderx.market_research.events import (
    LLM_ANALYSIS_COMPLETED,
    LLM_ANALYSIS_UNAVAILABLE,
    emit_market_research_fact,
)
from traderx.market_research.llm_schema import minimized_prompt_evidence, validate_advisory_analysis
from traderx.market_research.model import (
    CoordinatedMarketResearchRun,
    LlmAnalysisAttempt,
    MarketResearchRun,
)
from traderx.notifications.router import notify_market_research_owners


def run_advisory_analysis(
    database: Session,
    run: MarketResearchRun,
    port: LlmAnalysisPort,
    *,
    evidence: dict[str, object],
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmAnalysisAttempt:
    return _attempt_analysis(
        database,
        run,
        port,
        evidence=evidence,
        now=now,
        maximum_attempts=3,
        explicit_retry=False,
        sleep=sleep,
    )


def retry_advisory_analysis(
    database: Session,
    run: MarketResearchRun,
    port: LlmAnalysisPort,
    *,
    evidence: dict[str, object],
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmAnalysisAttempt:
    return _attempt_analysis(
        database,
        run,
        port,
        evidence=evidence,
        now=now,
        maximum_attempts=1,
        explicit_retry=True,
        sleep=sleep,
    )


def _attempt_analysis(
    database: Session,
    run: MarketResearchRun,
    port: LlmAnalysisPort,
    *,
    evidence: dict[str, object],
    now: datetime,
    maximum_attempts: int,
    explicit_retry: bool,
    sleep: Callable[[float], None],
) -> LlmAnalysisAttempt:
    if run.coordinated_run_id is None:
        raise ValueError("advisory analysis requires a coordinated run pin")
    parent = database.get(CoordinatedMarketResearchRun, run.coordinated_run_id)
    if parent is None:
        raise ValueError("coordinated market research run does not exist")
    pin = _required_pin(parent)
    prompt_evidence = minimized_prompt_evidence(evidence)
    request = LlmAnalysisRequest(
        provider=pin["provider_key"],
        exact_model_id=pin["exact_model_id"],
        prompt_template_version=pin["prompt_template_version"],
        output_schema_version=pin["output_schema_version"],
        inference_policy_version=pin["inference_policy_version"],
        evidence=prompt_evidence,
        store=False,
    )
    request_hash = _hash(
        {
            "provider": request.provider,
            "model": request.exact_model_id,
            "prompt": request.prompt_template_version,
            "schema": request.output_schema_version,
            "inference": request.inference_policy_version,
            "evidence": request.evidence,
        }
    )
    last: LlmAnalysisAttempt | None = None
    start_number = int(
        database.scalar(
            select(func.coalesce(func.max(LlmAnalysisAttempt.attempt_number), 0)).where(
                LlmAnalysisAttempt.research_run_id == run.id
            )
        )
        or 0
    )
    run.llm_analysis_state = "RUNNING"
    for offset in range(1, maximum_attempts + 1):
        try:
            response = port.analyze(request)
        except Exception:
            response = LlmAnalysisResponse(
                "FAILED",
                None,
                reason="ADVISORY_PROVIDER_FAILURE",
            )
        state = response.state
        analysis: dict[str, object] | None = None
        failure_reason = response.reason
        if response.state == "COMPLETED":
            try:
                analysis = validate_advisory_analysis(response.analysis)
            except ValidationError:
                state = "OUTPUT_INVALID"
                failure_reason = "OUTPUT_SCHEMA_VALIDATION_FAILED"
        attempt = LlmAnalysisAttempt(
            research_run_id=run.id,
            attempt_number=start_number + offset,
            provider_key=pin["provider_key"],
            exact_model_id=pin["exact_model_id"],
            catalogue_revision=pin["catalogue_revision"],
            adapter_revision=pin["adapter_revision"],
            prompt_template_version=pin["prompt_template_version"],
            output_schema_version=pin["output_schema_version"],
            inference_policy_version=pin["inference_policy_version"],
            state=state,
            request_hash=request_hash,
            response_hash=_hash(analysis) if analysis is not None else None,
            provider_request_id=response.provider_request_id,
            usage=dict(response.usage),
            analysis=analysis,
            failure_reason=failure_reason,
            started_at=now,
            finished_at=now,
            explicit_retry=explicit_retry,
        )
        database.add(attempt)
        database.flush()
        last = attempt
        if state == "COMPLETED":
            run.llm_analysis_state = "COMPLETED"
            emit_market_research_fact(
                database,
                aggregate_type="market_research_run",
                aggregate_id=run.id,
                aggregate_version=run.version,
                event_type=LLM_ANALYSIS_COMPLETED,
                data={
                    "category": run.category,
                    "provider": pin["provider_key"],
                    "exact_model_id": pin["exact_model_id"],
                    "response_hash": attempt.response_hash,
                    "authoritative": False,
                },
                now=now,
                correlation_id="market-research-llm",
            )
            database.flush()
            return attempt
        if offset < maximum_attempts:
            sleep(float(response.retry_after_seconds or 0))
    assert last is not None
    run.llm_analysis_state = "UNAVAILABLE"
    emit_market_research_fact(
        database,
        aggregate_type="market_research_run",
        aggregate_id=run.id,
        aggregate_version=run.version,
        event_type=LLM_ANALYSIS_UNAVAILABLE,
        data={
            "category": run.category,
            "provider": pin["provider_key"],
            "exact_model_id": pin["exact_model_id"],
            "failure_reason": last.failure_reason or last.state,
            "retry_eligible": True,
            "authoritative": False,
        },
        now=now,
        correlation_id="market-research-llm",
    )
    notify_market_research_owners(
        database,
        kind="LLM_UNAVAILABLE",
        subject_id=str(run.id),
        payload={
            "category": run.category,
            "provider": pin["provider_key"],
            "exact_model_id": pin["exact_model_id"],
            "failure_reason": last.failure_reason or last.state,
            "retry_eligible": True,
            "authoritative": False,
        },
        created_at=now,
    )
    database.flush()
    return last


def _required_pin(parent: CoordinatedMarketResearchRun) -> dict[str, str]:
    values = {
        "provider_key": parent.llm_provider_key,
        "exact_model_id": parent.exact_model_id,
        "catalogue_revision": parent.llm_catalogue_revision,
        "adapter_revision": parent.llm_adapter_revision,
        "prompt_template_version": parent.prompt_template_version,
        "output_schema_version": parent.output_schema_version,
        "inference_policy_version": parent.inference_policy_version,
    }
    if any(value is None for value in values.values()):
        raise ValueError("coordinated run has no complete advisory model pin")
    return {key: str(value) for key, value in values.items()}


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
