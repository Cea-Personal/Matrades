"""Owner-authorized policy for automatic, non-executing strategy validation."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyAutomationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    backtest_lookback_days: int = Field(default=90, ge=7, le=365)
    paper_duration_days: int = Field(default=30, ge=1, le=90)
    max_paper_attempts: int = Field(default=1, ge=1, le=5)
    spread: Decimal = Field(default=Decimal("0.0001"), ge=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal = Field(default=Decimal("0.00005"), ge=0)

    @model_validator(mode="after")
    def conservative_costs(self):
        if self.enabled and self.spread + self.commission + self.slippage <= 0:
            raise ValueError("autonomous validation requires non-zero transaction costs")
        return self


def automation_policy(account_data: dict) -> StrategyAutomationPolicy:
    return StrategyAutomationPolicy.model_validate(
        account_data.get("strategy_validation_automation", {})
    )
