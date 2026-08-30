"""Trade Plan construction boundary.

The builder binds deterministic risk output, immutable evidence references,
instrument authority, and an optional atomic risk reservation before a plan
can reach execution authorization.
"""

from modules.trading.trade_plans import build_trade_plan

__all__ = ["build_trade_plan"]
