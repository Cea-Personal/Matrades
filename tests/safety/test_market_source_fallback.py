from __future__ import annotations

from datetime import UTC, datetime, timedelta

from traderx.integrations.ports import SourceSemantics
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    SourceRole,
    build_source_evidence,
)
from traderx.market_research.source_selection import SourceAttempt, select_market_source

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _evidence(
    provider: str,
    capability: str,
    role: SourceRole,
    *,
    age: timedelta = timedelta(seconds=1),
    maximum_age: timedelta = timedelta(seconds=60),
    complete: bool = True,
) -> object:
    return build_source_evidence(
        provider=provider,
        capability=capability,
        semantics=(
            SourceSemantics.BROKER_PROXY
            if provider == "MT5_TERMINAL_BRIDGE"
            else SourceSemantics.ACTUAL
        ),
        source_role=role,
        observed_at=NOW - age,
        received_at=NOW,
        evaluated_at=NOW,
        policy=FreshnessPolicy(provider, capability, "policy-v1", maximum_age),
        entitlement_status="VERIFIED" if provider != "MT5_TERMINAL_BRIDGE" else "NOT_REQUIRED",
        complete=complete,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
        fallback_reason="SPECIALIST_RETRIES_EXHAUSTED" if role != SourceRole.SPECIALIST_PRIMARY else None,
    )


def test_fallback_uses_current_mt5_then_fresh_cache_after_three_specialist_attempts() -> None:
    failures = [SourceAttempt("CME_GROUP", index, False, "TIMEOUT") for index in range(1, 4)]
    mt5 = [_evidence("MT5_TERMINAL_BRIDGE", "BROKER_ACTIVITY", SourceRole.FALLBACK_MT5)]
    cached = [
        _evidence(
            "CME_GROUP",
            "OPEN_INTEREST",
            SourceRole.FALLBACK_CACHED_EXTERNAL,
            age=timedelta(hours=2),
            maximum_age=timedelta(days=1),
        )
    ]

    selected = select_market_source(
        specialist_attempts=failures,
        specialist_evidence=[],
        mt5_evidence=mt5,
        cached_external_evidence=cached,
        required_capabilities={"BROKER_ACTIVITY"},
    )
    assert selected.role == SourceRole.FALLBACK_MT5
    assert selected.blocked is False
    assert selected.active_assignment_changed is False

    selected_cache = select_market_source(
        specialist_attempts=failures,
        specialist_evidence=[],
        mt5_evidence=[
            _evidence(
                "MT5_TERMINAL_BRIDGE",
                "BROKER_ACTIVITY",
                SourceRole.FALLBACK_MT5,
                complete=False,
            )
        ],
        cached_external_evidence=cached,
        required_capabilities={"OPEN_INTEREST"},
    )
    assert selected_cache.role == SourceRole.FALLBACK_CACHED_EXTERNAL
    assert [step.role for step in selected_cache.trail] == [
        SourceRole.SPECIALIST_PRIMARY,
        SourceRole.FALLBACK_MT5,
        SourceRole.FALLBACK_CACHED_EXTERNAL,
    ]


def test_fallback_never_extends_freshness_or_weakens_required_capabilities() -> None:
    stale_cache = [
        _evidence(
            "CME_GROUP",
            "OPEN_INTEREST",
            SourceRole.FALLBACK_CACHED_EXTERNAL,
            age=timedelta(days=2),
            maximum_age=timedelta(days=1),
        )
    ]
    selected = select_market_source(
        specialist_attempts=[SourceAttempt("CME_GROUP", 3, False, "TIMEOUT")],
        specialist_evidence=[],
        mt5_evidence=[],
        cached_external_evidence=stale_cache,
        required_capabilities={"OPEN_INTEREST", "TRADED_VOLUME"},
    )
    assert selected.blocked is True
    assert selected.role is None
    assert "NO_COMPLETE_FRESH_FALLBACK" in selected.reason_codes
    assert selected.active_assignment_changed is False
