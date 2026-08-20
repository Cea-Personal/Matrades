from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.integrations.ports import LlmAnalysisRequest, LlmAnalysisResponse
from traderx.market_research.coordinator import create_coordinated_run
from traderx.market_research.llm_analysis import retry_advisory_analysis, run_advisory_analysis
from traderx.market_research.model import LlmAnalysisAttempt, MarketResearchRun
from traderx.shared.db import Base, load_model_metadata


class FakeLlmPort:
    def __init__(self, responses: list[LlmAnalysisResponse]) -> None:
        self.responses = responses
        self.requests: list[LlmAnalysisRequest] = []

    def test_connection(self, exact_model_id: str) -> dict[str, object]:
        return {"model": exact_model_id, "healthy": True}

    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class FailingLlmPort:
    def test_connection(self, exact_model_id: str) -> dict[str, object]:
        return {"model": exact_model_id, "healthy": False}

    def analyze(self, request: LlmAnalysisRequest) -> LlmAnalysisResponse:
        raise RuntimeError("provider response must not escape the advisory boundary")


def _run(database: Session, now: datetime) -> MarketResearchRun:
    account = TradingAccount(
        name="Demo",
        mode="DEMO",
        currency="USD",
        starting_balance=Decimal("10000"),
    )
    database.add(account)
    database.flush()
    parent = create_coordinated_run(
        database,
        account_id=account.id,
        trigger="MANUAL",
        methodology_version="market-suitability-v2",
        source_catalogue_revision="catalogue-v1",
        freshness_policy_manifest={"default": "freshness-v1"},
        retry_policy_manifest={"default": "retry-v1"},
        now=now,
        llm_pin={
            "provider_key": "OPENAI_RESPONSES",
            "exact_model_id": "gpt-5.6-terra",
            "catalogue_revision": "catalogue-v1",
            "adapter_revision": "adapter-v1",
            "prompt_template_version": "prompt-v1",
            "output_schema_version": "schema-v1",
            "inference_policy_version": "inference-v1",
        },
    )
    run = database.scalar(
        select(MarketResearchRun).where(
            MarketResearchRun.coordinated_run_id == parent.id,
            MarketResearchRun.category == "FOREX",
        )
    )
    assert run is not None
    run.deterministic_result_hash = "deterministic-result-hash"
    run.state = "COMPLETED"
    return run


def test_invalid_and_rate_limited_analysis_retries_same_pinned_model_without_mutation() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    port = FakeLlmPort(
        [
            LlmAnalysisResponse("COMPLETED", {"summary": 7}),
            LlmAnalysisResponse("RATE_LIMITED", None, retry_after_seconds=1, reason="RATE_LIMIT"),
            LlmAnalysisResponse(
                "COMPLETED",
                {
                    "summary": "Deterministic evidence is coherent.",
                    "anomalies": [],
                    "cautions": [],
                    "method_proposals": [],
                },
            ),
        ]
    )
    with Session(engine) as database, database.begin():
        run = _run(database, now)
        completed = run_advisory_analysis(
            database,
            run,
            port,
            evidence={"category": "FOREX", "deterministic_rank": ["EURUSD"]},
            now=now,
            sleep=lambda _seconds: None,
        )
        assert completed.state == "COMPLETED"
        assert run.llm_analysis_state == "COMPLETED"
        assert run.deterministic_result_hash == "deterministic-result-hash"
        assert {request.exact_model_id for request in port.requests} == {"gpt-5.6-terra"}
        assert all(request.store is False for request in port.requests)
        assert len(list(database.scalars(select(LlmAnalysisAttempt)))) == 3


def test_exhaustion_is_visible_and_explicit_retry_uses_original_pin() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    unavailable = FakeLlmPort(
        [LlmAnalysisResponse("TIMED_OUT", None, reason="TIMED_OUT") for _ in range(3)]
    )
    with Session(engine) as database, database.begin():
        run = _run(database, now)
        result = run_advisory_analysis(
            database,
            run,
            unavailable,
            evidence={"category": "FOREX"},
            now=now,
            sleep=lambda _seconds: None,
        )
        assert result.state == "TIMED_OUT"
        assert run.llm_analysis_state == "UNAVAILABLE"

        retry_port = FakeLlmPort(
            [
                LlmAnalysisResponse(
                    "COMPLETED",
                    {
                        "summary": "Retry completed.",
                        "anomalies": [],
                        "cautions": [],
                        "method_proposals": [],
                    },
                )
            ]
        )
        retried = retry_advisory_analysis(
            database,
            run,
            retry_port,
            evidence={"category": "FOREX"},
            now=now,
            sleep=lambda _seconds: None,
        )
        assert retried.explicit_retry is True
        assert retry_port.requests[0].exact_model_id == "gpt-5.6-terra"
        assert run.deterministic_result_hash == "deterministic-result-hash"


def test_provider_failure_cannot_roll_back_the_deterministic_result() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        run = _run(database, now)
        result = run_advisory_analysis(
            database,
            run,
            FailingLlmPort(),
            evidence={"category": "FOREX"},
            now=now,
            sleep=lambda _seconds: None,
        )

        assert result.state == "FAILED"
        assert result.failure_reason == "ADVISORY_PROVIDER_FAILURE"
        assert run.llm_analysis_state == "UNAVAILABLE"
        assert run.deterministic_result_hash == "deterministic-result-hash"
