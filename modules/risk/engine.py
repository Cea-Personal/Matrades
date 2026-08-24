from __future__ import annotations

from decimal import Decimal

from modules.policy.effective_limits import strictest_applicable
from modules.policy.models import ConstraintKind
from modules.risk.drawdown import daily_loss, total_drawdown
from modules.risk.exposure import aggregate_exposure
from modules.risk.models import CandidateTrade, RiskContext, RiskDecision, RiskResult, RiskSnapshot
from modules.risk.position_sizing import compliant_size
from modules.risk.reserved_risk import reserved_risk
from modules.risk.trade_capacity import additional_trade_capacity


class RiskEngine:
    """Deterministic authority. More restrictive applicable capacity always wins."""

    def evaluate(self, context: RiskContext, candidate: CandidateTrade) -> RiskResult:
        limits = strictest_applicable(context.constraints)
        required = {
            ConstraintKind.MAX_TOTAL_DRAWDOWN,
            ConstraintKind.MAX_DAILY_LOSS,
            ConstraintKind.MAX_PORTFOLIO_RISK,
        }
        missing = sorted(kind.value for kind in required - limits.keys())
        if missing:
            return self._missing_authority(context, candidate, missing)
        equity = context.account.current_equity
        drawdown = total_drawdown(context.account.starting_balance, equity)
        used_daily = daily_loss(context.account.realized_daily_pnl, context.account.floating_pnl)
        max_dd = limits.get(ConstraintKind.MAX_TOTAL_DRAWDOWN)
        max_daily = limits.get(ConstraintKind.MAX_DAILY_LOSS)
        max_portfolio = limits.get(ConstraintKind.MAX_PORTFOLIO_RISK)
        assert max_dd is not None and max_daily is not None and max_portfolio is not None
        allowed_dd = max_dd.value
        allowed_daily = max_daily.value
        allowed_portfolio = max_portfolio.value
        remaining_dd = max(Decimal("0"), allowed_dd - drawdown)
        remaining_daily = max(Decimal("0"), allowed_daily - used_daily)
        try:
            existing = reserved_risk(context.positions, context.include_unrealized_profit)
        except ValueError as exc:
            return self._blocked(
                context,
                candidate,
                drawdown,
                allowed_dd,
                remaining_dd,
                used_daily,
                remaining_daily,
                Decimal("Infinity"),
                str(exc),
            )
        remaining_portfolio = max(Decimal("0"), allowed_portfolio - existing)
        requested_risk = candidate.requested_size * candidate.risk_per_unit
        capacities = [remaining_dd, remaining_daily, remaining_portfolio]
        exposures = aggregate_exposure(context.positions, candidate, requested_risk)
        correlation_remaining: list[Decimal] = []
        violations: list[str] = []
        for group, cap in context.correlation_caps.items():
            without_candidate = aggregate_exposure(context.positions).get(group, Decimal("0"))
            correlation_remaining.append(max(Decimal("0"), cap - without_candidate))
            if exposures.get(group, Decimal("0")) > cap:
                violations.append(group)
        capacities.extend(correlation_remaining)
        size = compliant_size(
            candidate.requested_size, candidate.risk_per_unit, capacities, candidate.size_increment
        )
        approved_risk = size * candidate.risk_per_unit
        capacity = additional_trade_capacity(
            static_max=context.static_max_concurrent_trades,
            open_trades=len(context.positions),
            remaining_portfolio_risk=min(capacities),
            candidate_risk=max(approved_risk, requested_risk),
        )
        reasons: list[str] = []
        if size <= 0 or context.static_max_concurrent_trades <= len(context.positions):
            decision = RiskDecision.HARD_BLOCK
            size = Decimal("0")
            reasons.append("candidate would breach an applicable hard limit")
        elif size < candidate.requested_size:
            decision = RiskDecision.REDUCE_SIZE
            reasons.append("requested size reduced to the strictest remaining capacity")
        else:
            decision = RiskDecision.PASS
            reasons.append("candidate fits all current hard limits")
        limiting = [
            item.source
            for item in limits.values()
            if item.value in {allowed_dd, allowed_daily, allowed_portfolio}
        ]
        limiting.extend(violations)
        snapshot = RiskSnapshot(
            account_id=context.account.account_id,
            account_equity=equity,
            current_balance=context.account.current_balance,
            starting_account=context.account.starting_balance,
            floating_pnl=context.account.floating_pnl,
            realized_daily_pnl=context.account.realized_daily_pnl,
            current_drawdown=drawdown,
            daily_drawdown=used_daily,
            maximum_allowed_drawdown=allowed_dd,
            prop_firm_drawdown_limit=self._limit_from_source(context, "prop"),
            internal_drawdown_limit=self._limit_from_source(context, "internal"),
            remaining_drawdown=remaining_dd,
            daily_loss_used=used_daily,
            daily_loss_remaining=remaining_daily,
            existing_open_risk=existing,
            existing_correlated_exposure=aggregate_exposure(context.positions),
            candidate_trade_risk=size * candidate.risk_per_unit,
            portfolio_risk_after_trade=existing + size * candidate.risk_per_unit,
            remaining_total_loss_capacity=remaining_dd,
            remaining_portfolio_risk_capacity=remaining_portfolio,
            open_trades=len(context.positions),
            max_concurrent_trades=context.static_max_concurrent_trades,
            additional_trade_capacity=capacity,
            observed_at=context.account.observed_at.isoformat(),
            source=context.account.source,
            source_version=context.account.source_version,
            constraint_versions=sorted(
                f"{item.source}:{item.source_version}" for item in limits.values()
            ),
        )
        return RiskResult(
            decision=decision,
            approved_size=size,
            reasons=reasons,
            limiting_constraints=sorted(set(limiting)),
            snapshot=snapshot,
        )

    def _blocked(
        self,
        context: RiskContext,
        candidate: CandidateTrade,
        drawdown: Decimal,
        allowed_dd: Decimal,
        remaining_dd: Decimal,
        used_daily: Decimal,
        remaining_daily: Decimal,
        existing: Decimal,
        reason: str,
    ) -> RiskResult:
        return RiskResult(
            decision=RiskDecision.HARD_BLOCK,
            approved_size=Decimal("0"),
            reasons=[reason],
            limiting_constraints=["unbounded_open_position"],
            snapshot=RiskSnapshot(
                account_id=context.account.account_id,
                account_equity=context.account.current_equity,
                current_balance=context.account.current_balance,
                starting_account=context.account.starting_balance,
                floating_pnl=context.account.floating_pnl,
                realized_daily_pnl=context.account.realized_daily_pnl,
                current_drawdown=drawdown,
                daily_drawdown=used_daily,
                maximum_allowed_drawdown=allowed_dd,
                prop_firm_drawdown_limit=self._limit_from_source(context, "prop"),
                internal_drawdown_limit=self._limit_from_source(context, "internal"),
                remaining_drawdown=remaining_dd,
                daily_loss_used=used_daily,
                daily_loss_remaining=remaining_daily,
                existing_open_risk=existing,
                existing_correlated_exposure=aggregate_exposure(context.positions),
                candidate_trade_risk=Decimal("0"),
                portfolio_risk_after_trade=existing,
                remaining_total_loss_capacity=remaining_dd,
                remaining_portfolio_risk_capacity=Decimal("0"),
                open_trades=len(context.positions),
                max_concurrent_trades=context.static_max_concurrent_trades,
                additional_trade_capacity=0,
                observed_at=context.account.observed_at.isoformat(),
                source=context.account.source,
                source_version=context.account.source_version,
                constraint_versions=sorted(
                    f"{item.source}:{item.source_version}" for item in context.constraints
                ),
            ),
        )

    def _missing_authority(
        self, context: RiskContext, candidate: CandidateTrade, missing: list[str]
    ) -> RiskResult:
        drawdown = total_drawdown(
            context.account.starting_balance, context.account.current_equity
        )
        used_daily = daily_loss(
            context.account.realized_daily_pnl, context.account.floating_pnl
        )
        return self._blocked(
            context,
            candidate,
            drawdown,
            Decimal("0"),
            Decimal("0"),
            used_daily,
            Decimal("0"),
            Decimal("0"),
            f"required risk authority unavailable: {', '.join(missing)}",
        ).model_copy(update={"limiting_constraints": missing})

    @staticmethod
    def _limit_from_source(context: RiskContext, source_fragment: str) -> Decimal | None:
        candidates = [
            item.value
            for item in context.constraints
            if item.kind == ConstraintKind.MAX_TOTAL_DRAWDOWN
            and source_fragment in item.source.lower()
        ]
        return min(candidates) if candidates else None
