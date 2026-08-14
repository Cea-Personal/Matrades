from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.market_data.model import Instrument
from traderx.shared.events import append_outbox, event_envelope
from traderx.shared.types import ConcurrentModification, InvalidTransition, utc_now
from traderx.strategies.compiler import compile_strategy
from traderx.strategies.model import Strategy, StrategyLifecycle, StrategyVersion
from traderx.strategies.schema import StrategyDefinition

_ALLOWED: dict[StrategyLifecycle, set[StrategyLifecycle]] = {
    StrategyLifecycle.DRAFT: {
        StrategyLifecycle.RESEARCH,
        StrategyLifecycle.BACKTESTING,
        StrategyLifecycle.VALIDATING,
        StrategyLifecycle.RETIRED,
    },
    StrategyLifecycle.RESEARCH: {
        StrategyLifecycle.DRAFT,
        StrategyLifecycle.BACKTESTING,
        StrategyLifecycle.FAILED,
    },
    StrategyLifecycle.BACKTESTING: {
        StrategyLifecycle.VALIDATING,
        StrategyLifecycle.FAILED,
    },
    StrategyLifecycle.VALIDATING: {
        StrategyLifecycle.BACKTEST_PASSED,
        StrategyLifecycle.REJECTED,
        StrategyLifecycle.FAILED,
        StrategyLifecycle.DRAFT,
    },
    StrategyLifecycle.BACKTEST_PASSED: {
        StrategyLifecycle.PAPER_READY,
        StrategyLifecycle.RETIRED,
        StrategyLifecycle.STALE,
    },
    StrategyLifecycle.PAPER_READY: {
        StrategyLifecycle.PAPER_TRADING,
        StrategyLifecycle.STALE,
    },
    StrategyLifecycle.PAPER_TRADING: {
        StrategyLifecycle.PAPER_PASSED,
        StrategyLifecycle.REJECTED,
        StrategyLifecycle.FAILED,
    },
    StrategyLifecycle.PAPER_PASSED: {
        StrategyLifecycle.AWAITING_APPROVAL,
        StrategyLifecycle.REJECTED,
    },
    StrategyLifecycle.AWAITING_APPROVAL: {
        StrategyLifecycle.LIVE_APPROVED,
        StrategyLifecycle.REJECTED,
        StrategyLifecycle.RESEARCH,
        StrategyLifecycle.STALE,
    },
    StrategyLifecycle.LIVE_APPROVED: {
        StrategyLifecycle.LIVE,
        StrategyLifecycle.SUSPENDED,
        StrategyLifecycle.RETIRED,
        StrategyLifecycle.STALE,
    },
    StrategyLifecycle.LIVE: {
        StrategyLifecycle.WATCH,
        StrategyLifecycle.SUSPENDED,
        StrategyLifecycle.RETIRED,
        StrategyLifecycle.STALE,
    },
    StrategyLifecycle.WATCH: {
        StrategyLifecycle.LIVE,
        StrategyLifecycle.SUSPENDED,
        StrategyLifecycle.RETIRED,
    },
    StrategyLifecycle.SUSPENDED: {StrategyLifecycle.RESEARCH, StrategyLifecycle.RETIRED},
    StrategyLifecycle.FAILED: {StrategyLifecycle.DRAFT, StrategyLifecycle.RETIRED},
    StrategyLifecycle.REJECTED: {StrategyLifecycle.DRAFT, StrategyLifecycle.RETIRED},
    StrategyLifecycle.STALE: {StrategyLifecycle.RESEARCH, StrategyLifecycle.RETIRED},
    StrategyLifecycle.RETIRED: set(),
}


@dataclass(frozen=True, slots=True)
class VersionState:
    version: int
    definition_hash: str
    lifecycle: StrategyLifecycle


def transition(
    state: VersionState, target: StrategyLifecycle, *, evidence_passed: bool
) -> VersionState:
    if target not in _ALLOWED[state.lifecycle]:
        raise InvalidTransition(f"cannot transition strategy from {state.lifecycle} to {target}")
    if (
        target
        in {
            StrategyLifecycle.QUALIFIED,
            StrategyLifecycle.AWAITING_APPROVAL,
            StrategyLifecycle.LIVE_ELIGIBLE,
        }
        and not evidence_passed
    ):
        raise InvalidTransition("required validation evidence has not passed")
    return replace(state, lifecycle=target)


def immutable_edit(state: VersionState, definition_hash: str) -> VersionState:
    if definition_hash == state.definition_hash:
        raise ValueError("an immutable edit must change the strategy definition")
    return VersionState(state.version + 1, definition_hash, StrategyLifecycle.DRAFT)


def create_strategy_with_version(
    database: Session,
    actor: Actor,
    *,
    name: str,
    instrument_id: UUID,
    definition_payload: dict[str, object],
    change_summary: str,
    idempotency_key: str,
    correlation_id: str,
) -> tuple[Strategy, StrategyVersion]:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "strategy.create", require_mfa=True)
    if database.get(Instrument, instrument_id) is None:
        raise InvalidTransition("the selected instrument does not exist")
    if database.scalar(select(Strategy.id).where(func.lower(Strategy.name) == name.lower())):
        raise InvalidTransition("a strategy with this name already exists")
    definition = definition_from_payload(definition_payload)
    compiled = compile_strategy(definition)
    now = utc_now()
    strategy = Strategy(
        name=name.strip(), instrument_id=instrument_id, owner_id=actor.id, created_at=now
    )
    database.add(strategy)
    database.flush()
    version = StrategyVersion(
        strategy_id=strategy.id,
        sequence=1,
        definition=definition.canonical(),
        definition_hash=compiled.definition_hash,
        lifecycle=StrategyLifecycle.DRAFT,
        parent_version_id=None,
        change_summary=change_summary,
        author_id=actor.id,
        created_at=now,
    )
    database.add(version)
    database.flush()
    _record_strategy_version(
        database,
        actor,
        strategy,
        version,
        reason=change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return strategy, version


def create_immutable_version(
    database: Session,
    actor: Actor,
    *,
    strategy_id: UUID,
    expected_etag: str,
    definition_payload: dict[str, object],
    change_summary: str,
    idempotency_key: str,
    correlation_id: str,
) -> StrategyVersion:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "strategy.version.create", require_mfa=True)
    strategy = database.get(Strategy, strategy_id)
    if strategy is None:
        raise InvalidTransition("the requested strategy does not exist")
    if expected_etag != f'"strategy-{strategy.id}-{strategy.version}"':
        raise ConcurrentModification("the strategy changed; refresh before creating a version")
    latest = database.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(StrategyVersion.sequence.desc())
        .limit(1)
    )
    if latest is None:
        raise InvalidTransition("the strategy has no source version")
    definition = definition_from_payload(definition_payload)
    compiled = compile_strategy(definition)
    if compiled.definition_hash == latest.definition_hash:
        raise InvalidTransition("the new immutable version must change the strategy definition")
    version = StrategyVersion(
        strategy_id=strategy.id,
        sequence=latest.sequence + 1,
        definition=definition.canonical(),
        definition_hash=compiled.definition_hash,
        lifecycle=StrategyLifecycle.DRAFT,
        parent_version_id=latest.id,
        change_summary=change_summary,
        author_id=actor.id,
        created_at=utc_now(),
    )
    database.add(version)
    # Advance the aggregate version so concurrent child-version creation fails closed.
    strategy.version += 1
    database.flush()
    _record_strategy_version(
        database,
        actor,
        strategy,
        version,
        reason=change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    return version


def definition_from_payload(payload: dict[str, object]) -> StrategyDefinition:
    try:
        return StrategyDefinition(
            regime=str(payload["regime"]),
            timeframes=tuple(str(value) for value in _list(payload.get("timeframes"))),
            conditions=tuple(_mapping(value) for value in _list(payload.get("conditions"))),
            direction=str(payload.get("direction", "BOTH")).upper(),
            filters=tuple(_mapping(value) for value in _list(payload.get("filters"))),
            stop=_mapping(payload.get("stop")),
            target=_mapping(payload.get("target")),
            invalidation=_mapping(payload.get("invalidation")),
            expiration=_mapping(payload.get("expiration")),
            risk_fraction=Decimal(str(payload.get("risk_fraction", "0.01"))),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidTransition("the strategy definition is incomplete or invalid") from error


def strategy_payload(database: Session, strategy: Strategy) -> dict[str, object]:
    versions = list(
        database.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.id)
            .order_by(StrategyVersion.sequence.desc())
        )
    )
    return {
        "id": str(strategy.id),
        "name": strategy.name,
        "instrument_id": str(strategy.instrument_id) if strategy.instrument_id else None,
        "version": strategy.version,
        "etag": f'"strategy-{strategy.id}-{strategy.version}"',
        "versions": [strategy_version_payload(version) for version in versions],
        "created_at": strategy.created_at.isoformat(),
    }


def strategy_version_payload(version: StrategyVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "strategy_id": str(version.strategy_id),
        "sequence": version.sequence,
        "row_version": version.version,
        "definition": version.definition,
        "definition_hash": version.definition_hash,
        "lifecycle": version.lifecycle,
        "parent_version_id": str(version.parent_version_id) if version.parent_version_id else None,
        "change_summary": version.change_summary,
        "created_at": version.created_at.isoformat(),
        "etag": f'"strategy-version-{version.id}-{version.version}"',
        "immutable": True,
    }


def _record_strategy_version(
    database: Session,
    actor: Actor,
    strategy: Strategy,
    version: StrategyVersion,
    *,
    reason: str,
    idempotency_key: str,
    correlation_id: str,
) -> None:
    now = utc_now()
    evidence = {
        "strategy_id": str(strategy.id),
        "strategy_version_id": str(version.id),
        "sequence": version.sequence,
        "definition_hash": version.definition_hash,
    }
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role.value,
            action="strategy.version.create",
            outcome="SUCCEEDED",
            target_type="strategy_version",
            target_id=version.id,
            target_version=version.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=None,
            new_value=evidence,
            occurred_at=now,
        )
    )
    envelope = event_envelope(
        source="urn:traderx:strategies",
        event_type="com.traderx.strategy.version-created.v1",
        subject=f"strategies/{strategy.id}/versions/{version.id}",
        data=evidence,
        now=now,
        correlation_id=correlation_id,
        actor_id=actor.id,
        aggregate_version=version.version,
    )
    append_outbox(
        database,
        aggregate_type="strategy_version",
        aggregate_id=version.id,
        aggregate_version=version.version,
        event_type=str(envelope["type"]),
        envelope=envelope,
    )


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return value


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return {str(key): item for key, item in value.items()}
