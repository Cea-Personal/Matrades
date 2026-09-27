"""Durable opt-in orchestration from accepted research through paper review."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from apps.worker.app.celery_app import celery_app
from modules.identity.authorization import Actor, Role
from modules.strategies.autonomy import automation_policy
from modules.strategies.monitoring import validation_passed
from packages.shared.database import session_factory, unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification


async def _account_for_draft(store: ResourceStore, draft: ResourceRecord):
    account_id = draft.data.get("research_basis", {}).get("account_id")
    return await store.get("account", UUID(str(account_id)), draft.owner_id) if account_id else None


async def _advance_draft(draft_id: UUID) -> str:
    # Local import avoids coupling API startup to Celery task discovery.
    from apps.api.app.routes.strategies import (
        BacktestInput,
        create_backtest,
        submit,
    )

    owner_id = None
    account = None
    policy_saved_at = None
    async with session_factory() as db:
        try:
            draft = await db.scalar(
                select(ResourceRecord)
                .where(
                    ResourceRecord.id == draft_id,
                    ResourceRecord.kind == "strategy_draft",
                )
                .with_for_update()
            )
            if draft is None or draft.state != "AWAITING_STRATEGY_APPROVAL":
                return "INACTIVE"
            owner_id = draft.owner_id
            store = ResourceStore(db)
            account = await _account_for_draft(store, draft)
            if (
                account is None
                or account.state == "DELETED"
                or not automation_policy(account.data).enabled
            ):
                return "MANUAL"
            policy = automation_policy(account.data)
            policy_saved_at = account.data.get("strategy_validation_automation_saved_at")
            actor = Actor(
                UUID(
                    account.data.get("strategy_validation_automation_saved_by", str(draft.owner_id))
                ),
                draft.owner_id,
                Role.OWNER,
            )
            spec = StrategySpecification.model_validate(draft.data["proposed_specification"])
            await store.update(
                draft,
                {
                    **draft.data,
                    "specification": spec.model_dump(mode="json"),
                    "lifecycle_state": "DRAFT",
                    "provenance": {
                        **draft.data.get("provenance", {}),
                        "human_approval": "NOT_REQUESTED",
                        "approval_authority": "AUTOMATION_POLICY",
                        "policy_saved_at": account.data.get(
                            "strategy_validation_automation_saved_at"
                        ),
                    },
                },
                state="DRAFT",
                event_type="strategy.accepted_by_automation_policy",
            )
            version_data = await submit(draft.id, actor, db)
            version_id = UUID(version_data["id"])
            basis = version_data.get("research_basis", {})
            now = datetime.now(UTC)
            await create_backtest(
                version_id,
                BacktestInput(
                    instrument=str(basis["instrument"]),
                    start_at=now - timedelta(days=policy.backtest_lookback_days),
                    end_at=now,
                    timeframe=str(basis.get("historical_timeframe", "1h")),
                    initial_equity=Decimal(str(account.data["starting_balance"])),
                    spread=policy.spread,
                    commission=policy.commission,
                    slippage=policy.slippage,
                    max_daily_loss=await _loss_limit(
                        store, draft.owner_id, account.id, "MAX_DAILY_LOSS"
                    ),
                    max_total_loss=await _loss_limit(
                        store, draft.owner_id, account.id, "MAX_TOTAL_DRAWDOWN"
                    ),
                ),
                actor,
                db,
            )
            return "BACKTESTING"
        except Exception as exc:
            await db.rollback()
            async with db.begin():
                draft = (
                    await ResourceStore(db).get("strategy_draft", draft_id, owner_id)
                    if owner_id
                    else None
                )
                if draft is not None:
                    await ResourceStore(db).update(
                        draft,
                        {
                            **draft.data,
                            "automation_failure": (
                                str(exc)[:300] if type(exc) is ValueError else type(exc).__name__
                            ),
                            "automation_failure_policy_saved_at": policy_saved_at,
                        },
                        event_type="strategy.automation_blocked",
                    )
            return "BLOCKED"


async def _loss_limit(store, owner_id, account_id, kind: str) -> Decimal:
    values = []
    for resource_kind in ("prop_ruleset", "guardrail"):
        for record in await store.list(resource_kind, owner_id):
            if record.state != "ACTIVE" or record.data.get("account_id") not in {
                None,
                str(account_id),
            }:
                continue
            values.extend(
                Decimal(str(rule["value"]))
                for rule in record.data.get("rules", [])
                if rule.get("kind") == kind and rule.get("enforcement", "HARD") == "HARD"
            )
    if not values:
        raise ValueError(f"autonomous validation requires an active {kind} policy")
    return min(values)


async def _start_paper(version_id: UUID) -> str:
    from apps.api.app.routes.strategies import PaperTradingInput, start_paper_trading

    async with session_factory() as db:
        version = await db.scalar(
            select(ResourceRecord).where(
                ResourceRecord.id == version_id,
                ResourceRecord.kind == "strategy_version",
            )
        )
        if version is None:
            return "INACTIVE"
        basis = version.data.get("research_basis", {})
        account_id = basis.get("account_id")
        store = ResourceStore(db)
        account = await store.get("account", UUID(str(account_id)), version.owner_id)
        if account is None or account.state == "DELETED":
            return "BLOCKED"
        policy = automation_policy(account.data)
        attempts = [
            item
            for item in await store.list("strategy_paper_run", version.owner_id)
            if item.data.get("strategy_version_id") == str(version.id)
        ]
        if not policy.enabled or len(attempts) >= policy.max_paper_attempts:
            return "MANUAL"
        actor = Actor(version.owner_id, version.owner_id, Role.OWNER)
        await start_paper_trading(
            version.id,
            PaperTradingInput(
                duration_days=policy.paper_duration_days,
                notes="Started by owner-authorized autonomous validation",
            ),
            actor,
            db,
        )
        return "PAPER_TRADING"


async def _retry_waiting_backtest(version_id: UUID) -> str:
    try:
        return await _queue_waiting_backtest(version_id)
    except Exception as exc:
        async with unit_of_work() as db:
            version = await db.scalar(
                select(ResourceRecord)
                .where(ResourceRecord.id == version_id, ResourceRecord.kind == "strategy_version")
                .with_for_update()
            )
            if version is None:
                return "INACTIVE"
            if (
                version.state != "VALIDATING"
                or version.data.get("latest_backtest_state") != "WAITING_FOR_DATA"
            ):
                return version.state
            store = ResourceStore(db)
            try:
                account_id = UUID(str(version.data.get("research_basis", {}).get("account_id")))
            except (ValueError, TypeError):
                account_id = None
            account = (
                await store.get("account", account_id, version.owner_id) if account_id else None
            )
            await store.update(
                version,
                {
                    **version.data,
                    "automation_failure": str(exc)[:300]
                    if type(exc) is ValueError
                    else type(exc).__name__,
                    "automation_failure_policy_saved_at": account.data.get(
                        "strategy_validation_automation_saved_at"
                    )
                    if account
                    else None,
                },
                event_type="strategy.validation_retry.blocked",
            )
        return "BLOCKED"


async def _queue_waiting_backtest(version_id: UUID) -> str:
    from apps.api.app.routes.strategies import BacktestInput, create_backtest

    async with session_factory() as db:
        version = await db.scalar(
            select(ResourceRecord)
            .where(ResourceRecord.id == version_id, ResourceRecord.kind == "strategy_version")
            .with_for_update()
        )
        if (
            version is None
            or version.state != "VALIDATING"
            or version.data.get("latest_backtest_state") != "WAITING_FOR_DATA"
        ):
            return "INACTIVE"
        store = ResourceStore(db)
        basis = version.data.get("research_basis", {})
        account = await store.get("account", UUID(str(basis["account_id"])), version.owner_id)
        if (
            account is None
            or account.state == "DELETED"
            or not automation_policy(account.data).enabled
        ):
            return "MANUAL"
        if version.data.get("automation_failure") and version.data.get(
            "automation_failure_policy_saved_at"
        ) == account.data.get("strategy_validation_automation_saved_at"):
            return "BLOCKED"
        now = datetime.now(UTC)
        if (
            not version.data.get("validation_retry_after_at")
            or datetime.fromisoformat(version.data["validation_retry_after_at"]) > now
        ):
            return "WAITING_FOR_DATA"
        policy = automation_policy(account.data)
        await create_backtest(
            version.id,
            BacktestInput(
                instrument=basis["instrument"],
                start_at=now - timedelta(days=policy.backtest_lookback_days),
                end_at=now,
                timeframe=basis.get("historical_timeframe", "1h"),
                initial_equity=Decimal(str(account.data["starting_balance"])),
                spread=policy.spread,
                commission=policy.commission,
                slippage=policy.slippage,
                max_daily_loss=await _loss_limit(
                    store, version.owner_id, account.id, "MAX_DAILY_LOSS"
                ),
                max_total_loss=await _loss_limit(
                    store, version.owner_id, account.id, "MAX_TOTAL_DRAWDOWN"
                ),
            ),
            Actor(version.owner_id, version.owner_id, Role.OWNER),
            db,
        )
        return "BACKTESTING"


async def _review_paper(version_id: UUID, run_id: UUID) -> str:
    from apps.api.app.routes.strategies import PaperEvidenceInput, complete_paper_trading

    async with session_factory() as db:
        version = await db.scalar(
            select(ResourceRecord).where(
                ResourceRecord.id == version_id,
                ResourceRecord.kind == "strategy_version",
            )
        )
        if version is None:
            return "INACTIVE"
        account_id = version.data.get("research_basis", {}).get("account_id")
        account = await ResourceStore(db).get("account", UUID(str(account_id)), version.owner_id)
        if (
            account is None
            or account.state == "DELETED"
            or not automation_policy(account.data).enabled
        ):
            return "MANUAL"
        result = await complete_paper_trading(
            version.id,
            run_id,
            PaperEvidenceInput(),
            Actor(version.owner_id, version.owner_id, Role.OWNER),
            db,
        )
        await db.commit()
        return str(result["strategy"]["state"])


async def _schedule() -> list[str]:
    actions = []
    async with unit_of_work() as db:
        records = list(
            await db.scalars(
                select(ResourceRecord).where(
                    ResourceRecord.kind.in_(["strategy_draft", "strategy_version"])
                )
            )
        )
        runs = {
            str(item.id): item
            for item in await db.scalars(
                select(ResourceRecord).where(ResourceRecord.kind == "strategy_paper_run")
            )
        }
        accounts = {
            (item.owner_id, str(item.id)): item
            for item in await db.scalars(
                select(ResourceRecord).where(
                    ResourceRecord.kind == "account", ResourceRecord.state != "DELETED"
                )
            )
        }
    now = datetime.now(UTC)
    for record in records:
        account_id = record.data.get("research_basis", {}).get("account_id")
        account = accounts.get((record.owner_id, str(account_id)))
        if account is None:
            continue
        policy = automation_policy(account.data)
        if not policy.enabled:
            continue
        if record.data.get("automation_failure") and record.data.get(
            "automation_failure_policy_saved_at"
        ) == account.data.get("strategy_validation_automation_saved_at"):
            continue
        if record.kind == "strategy_draft" and record.state == "AWAITING_STRATEGY_APPROVAL":
            advance_strategy_draft.delay(str(record.id))
            actions.append(f"draft:{record.id}")
        elif (
            record.kind == "strategy_version"
            and record.state == "VALIDATING"
            and record.data.get("latest_backtest_state") == "WAITING_FOR_DATA"
        ):
            retry_at = record.data.get("validation_retry_after_at")
            if retry_at and datetime.fromisoformat(retry_at) <= now:
                retry_strategy_backtest.delay(str(record.id))
                actions.append(f"backtest-retry:{record.id}")
        elif (
            record.kind == "strategy_version"
            and record.state == "VALIDATING"
            and validation_passed(record.data.get("validation_evidence", {}))
        ):
            attempts = sum(
                run.data.get("strategy_version_id") == str(record.id) for run in runs.values()
            )
            if attempts >= policy.max_paper_attempts:
                continue
            start_strategy_paper.delay(str(record.id))
            actions.append(f"paper:{record.id}")
        elif record.kind == "strategy_version" and record.state == "PAPER_TRADING":
            run = runs.get(str(record.data.get("paper_run_id")))
            if (
                run
                and run.state == "RUNNING"
                and datetime.fromisoformat(run.data["entry_cutoff"]) <= now
                and not run.data.get("open_positions")
                and not run.data.get("pending_entries")
                and not run.data.get("failure")
            ):
                review_strategy_paper.delay(str(record.id), str(run.id))
                actions.append(f"review:{record.id}")
    return actions


@celery_app.task(name="apps.worker.app.tasks.strategy_autonomy.advance_strategy_draft")
def advance_strategy_draft(draft_id: str) -> str:
    return asyncio.run(_advance_draft(UUID(draft_id)))


@celery_app.task(name="apps.worker.app.tasks.strategy_autonomy.start_strategy_paper")
def start_strategy_paper(version_id: str) -> str:
    return asyncio.run(_start_paper(UUID(version_id)))


@celery_app.task(name="apps.worker.app.tasks.strategy_autonomy.retry_strategy_backtest")
def retry_strategy_backtest(version_id: str) -> str:
    return asyncio.run(_retry_waiting_backtest(UUID(version_id)))


@celery_app.task(name="apps.worker.app.tasks.strategy_autonomy.review_strategy_paper")
def review_strategy_paper(version_id: str, run_id: str) -> str:
    return asyncio.run(_review_paper(UUID(version_id), UUID(run_id)))


@celery_app.task(name="apps.worker.app.tasks.strategy_autonomy.schedule_strategy_autonomy")
def schedule_strategy_autonomy() -> list[str]:
    return asyncio.run(_schedule())
