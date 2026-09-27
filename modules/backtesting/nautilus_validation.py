"""Native event-driven order replay after quantitative research, never live execution."""

from __future__ import annotations

from bisect import bisect_right
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from modules.strategies.entry_context import entry_context_reason
from modules.strategies.pair_profile import news_features
from modules.strategies.signals import (
    entry_matches,
    matches,
    protection_levels,
    strategy_feature_series,
)


def validate_execution(
    strategy,
    candles,
    configuration,
    *,
    timeframe_seconds: int,
    contract: dict,
    calendar=None,
    validation_start_after=None,
    quotes: list[dict] | None = None,
) -> dict[str, Any]:
    import nautilus_trader
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.backtest.models import FeeModel, FillModel
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AccountType, AssetClass, BookType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import Cfd
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    from modules.backtesting.engine import validate_candles

    validate_candles(candles)
    if strategy.trade_rules is None:
        return {"engine": "NautilusTrader", "passed": False, "status": "UNSUPPORTED_PRICE_RULES"}
    required = (
        "tick_size",
        "price_currency",
        "quantity_step",
        "quantity_minimum",
        "contract_multiplier",
    )
    if any(contract.get(key) is None for key in required):
        return {
            "engine": "NautilusTrader",
            "passed": False,
            "status": "MISSING_BROKER_CONTRACT_TERMS",
            "required_terms": list(required),
            "execution_authorized": False,
        }
    tick = Decimal(str(contract["tick_size"]))
    multiplier = Decimal(str(contract["contract_multiplier"]))
    size_step = Decimal(str(contract["quantity_step"])) * multiplier
    min_size = Decimal(str(contract["quantity_minimum"])) * multiplier
    if not all(
        value.is_finite() and value > 0 for value in (tick, multiplier, size_step, min_size)
    ):
        raise ValueError("positive finite broker contract terms required")
    price_precision = max(0, -int(tick.normalize().as_tuple().exponent))
    size_precision = max(0, -int(size_step.normalize().as_tuple().exponent))
    currency = Currency.from_str(str(contract["price_currency"]))
    venue = Venue("MATRADES_RESEARCH")
    instrument_id = InstrumentId(Symbol(strategy.instruments[0].replace("/", "_")), venue)
    asset = {
        "FOREX": AssetClass.FX,
        "METALS": AssetClass.COMMODITY,
        "CRYPTOCURRENCY": AssetClass.CRYPTOCURRENCY,
        "STOCKS": AssetClass.EQUITY,
    }.get(str(strategy.asset_class), AssetClass.FX)
    instrument = Cfd(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.symbol,
        asset_class=asset,
        quote_currency=currency,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=Price(float(tick), price_precision),
        size_increment=Quantity(float(size_step), size_precision),
        ts_event=0,
        ts_init=0,
        min_quantity=Quantity(float(min_size), size_precision),
        margin_init=Decimal(".01"),
        margin_maint=Decimal(".005"),
    )
    bar_times = [int(c.observed_at.timestamp() * 1_000_000_000) for c in candles]
    last_time = bar_times[-1] + timeframe_seconds * 1_000_000_000 - 1
    cutoff = (
        int(validation_start_after.timestamp() * 1_000_000_000) if validation_start_after else 0
    )
    direction = strategy.trade_rules.direction
    feature_series = strategy_feature_series(strategy, candles)

    class PerUnitFee(FeeModel):  # type: ignore[misc]  # Native Cython base has no typing metadata.
        def get_commission(self, order, fill_qty, fill_px, instrument):
            return Money(fill_qty.as_decimal() * configuration.commission / 2, currency)

    class Replay(Strategy):  # type: ignore[misc]  # Native Cython base has no typing metadata.
        def __init__(self) -> None:
            super().__init__(StrategyConfig(order_id_tag="MR"))
            self.previous_bar = -1
            self.entry_id = None
            self.stop_order = None
            self.targets = set()
            self.active_features: dict[str, Decimal] | None = None
            self.entry_price: Decimal | None = None
            self.original_risk: Decimal | None = None
            self.position_risks = []
            self.closed_r = []
            self.fills = []
            self.rejections = []
            self.closed_positions = []
            self.partial_hits = 0
            self.equity_peak = configuration.initial_equity
            self.max_drawdown = Decimal(0)

        def on_start(self):
            self.subscribe_quote_ticks(instrument_id)

        def on_stop(self):
            self.cancel_all_orders(instrument_id)
            self.close_all_positions(instrument_id)

        def on_quote_tick(self, tick_event):
            account = self.portfolio.account(venue)
            unrealized = self.portfolio.unrealized_pnl(instrument_id)
            equity = account.balance_total(currency).as_decimal() + (
                unrealized.as_decimal() if unrealized is not None else Decimal(0)
            )
            self.equity_peak = max(self.equity_peak, equity)
            self.max_drawdown = max(self.max_drawdown, self.equity_peak - equity)
            index = bisect_right(bar_times, tick_event.ts_event) - 1
            if index < 1:
                return
            if tick_event.ts_event >= last_time:
                self.cancel_all_orders(instrument_id)
                self.close_all_positions(instrument_id)
                return
            if index == self.previous_bar:
                return
            self.previous_bar = index
            features = {
                **feature_series[index - 1],
                **news_features(strategy.instruments[0], candles[index].observed_at, calendar),
            }
            if self.portfolio.is_net_long(instrument_id) or self.portfolio.is_net_short(
                instrument_id
            ):
                if matches(strategy.exit, features) or matches(strategy.invalidation, features):
                    self.cancel_all_orders(instrument_id)
                    self.close_all_positions(instrument_id)
                elif self.stop_order is not None and strategy.position_management.get(
                    "trailing_stop"
                ):
                    if self.original_risk is None:
                        raise ValueError("trailing protection requires recorded entry risk")
                    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
                    candidate = candles[index - 1].close - sign * self.original_risk
                    current = self.stop_order.trigger_price.as_decimal()
                    improved = max(candidate, current) if sign > 0 else min(candidate, current)
                    if improved != current:
                        self.modify_order(
                            self.stop_order, trigger_price=instrument.make_price(float(improved))
                        )
                return
            if (
                self.entry_id is not None
                or tick_event.ts_event <= cutoff
                or features["volatility"] <= 0
            ):
                return
            if not entry_matches(strategy, features) or entry_context_reason(
                strategy, candles[index].observed_at, calendar
            ):
                return
            self.active_features = features
            risk = features["volatility"] * strategy.trade_rules.stop_volatility_multiple
            account = self.portfolio.account(venue)
            equity = account.balance_total(currency).as_decimal()
            desired = equity * strategy.risk_per_trade / 100 / risk
            units = (desired / size_step).to_integral_value(rounding=ROUND_FLOOR) * size_step
            # Every target must be representable at the broker's step/minimum.
            count = len(strategy.trade_rules.take_profit_r_multiples)
            if units < max(min_size * count, size_step * count):
                return
            maximum = contract.get("quantity_maximum")
            if maximum is not None:
                units = min(units, Decimal(str(maximum)) * multiplier)
                units = (units / size_step).to_integral_value(rounding=ROUND_FLOOR) * size_step
                if units < max(min_size * count, size_step * count):
                    return
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY if direction == "LONG" else OrderSide.SELL,
                quantity=instrument.make_qty(float(units)),
            )
            self.entry_id = order.client_order_id
            self.submit_order(order)

        def on_order_filled(self, event):
            self.fills.append(
                {
                    "time": str(event.ts_event),
                    "order_id": str(event.client_order_id),
                    "price": str(event.last_px),
                    "quantity": str(event.last_qty),
                    "commission": str(event.commission),
                }
            )
            if event.client_order_id == self.entry_id:
                if self.active_features is None:
                    raise ValueError("entry fill requires recorded decision features")
                self.entry_id = None
                entry_price: Decimal = event.last_px.as_decimal()
                self.entry_price = entry_price
                stop, targets = protection_levels(
                    strategy.trade_rules, entry_price, self.active_features["volatility"], tick
                )
                self.original_risk = abs(entry_price - stop)
                self.position_risks.append(self.original_risk * event.last_qty.as_decimal())
                self.partial_hits = 0
                side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
                self.stop_order = self.order_factory.stop_market(
                    instrument_id=instrument_id,
                    order_side=side,
                    quantity=event.last_qty,
                    trigger_price=instrument.make_price(float(stop)),
                    reduce_only=True,
                )
                self.submit_order(self.stop_order)
                quantity = event.last_qty.as_decimal()
                fraction = (quantity / len(targets) / size_step).to_integral_value(
                    rounding=ROUND_FLOOR
                ) * size_step
                for i, target in enumerate(targets):
                    size = (
                        quantity - fraction * (len(targets) - 1)
                        if i == len(targets) - 1
                        else fraction
                    )
                    order = self.order_factory.limit(
                        instrument_id=instrument_id,
                        order_side=side,
                        quantity=instrument.make_qty(float(size)),
                        price=instrument.make_price(float(target)),
                        post_only=False,
                        reduce_only=True,
                    )
                    self.targets.add(order.client_order_id)
                    self.submit_order(order)
            elif event.client_order_id in self.targets:
                self.partial_hits += 1
                if self.stop_order is not None and not self.stop_order.is_closed:
                    positions = self.cache.positions_open(instrument_id=instrument_id)
                    if positions:
                        kwargs = {"quantity": positions[0].quantity}
                        if strategy.position_management.get("move_to_break_even"):
                            if self.entry_price is None:
                                raise ValueError(
                                    "break-even protection requires recorded entry price"
                                )
                            kwargs["trigger_price"] = instrument.make_price(float(self.entry_price))
                        self.modify_order(self.stop_order, **kwargs)

        def on_position_closed(self, event):
            self.cancel_all_orders(instrument_id)
            positions = self.cache.positions_closed(instrument_id=instrument_id)
            latest = positions[-1] if positions else None
            if latest is not None:
                pnl = latest.realized_pnl.as_decimal()
                risk = self.position_risks[-1] if self.position_risks else Decimal(0)
                self.closed_positions.append(
                    {
                        "net_pnl": str(pnl),
                        "risk": str(risk),
                        "partial_targets_hit": self.partial_hits,
                    }
                )
                self.closed_r.append(float(pnl / risk) if risk else 0)
            self.stop_order = None
            self.targets.clear()

        def on_order_rejected(self, event):
            self.rejections.append(
                {"order_id": str(event.client_order_id), "reason": str(event.reason)[:160]}
            )
            if event.client_order_id == self.entry_id:
                self.entry_id = None

    def price(value: Decimal, side: str) -> Price:
        rounding = ROUND_FLOOR if side == "bid" else ROUND_CEILING
        rounded = (value / tick).to_integral_value(rounding=rounding) * tick
        if rounded <= 0:
            raise ValueError("execution costs produced a non-positive quote")
        return Price(float(rounded), price_precision)

    data = []
    if quotes is not None:
        if len(quotes) > 2_000_000:
            raise ValueError("tick replay budget exceeded; validate a smaller held-out interval")
        previous = -1
        for quote in quotes:
            at = quote["time"]
            if isinstance(at, str):
                at = datetime.fromisoformat(at)
            timestamp = int(at.astimezone(UTC).timestamp() * 1_000_000_000)
            if timestamp < previous:
                raise ValueError("quote replay must be chronological")
            previous = timestamp
            if not bar_times[0] <= timestamp <= last_time:
                continue
            bid, ask = Decimal(str(quote["bid"])), Decimal(str(quote["ask"]))
            if not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask:
                raise ValueError("invalid bid/ask execution evidence")
            data.append(
                QuoteTick(
                    instrument_id,
                    price(bid - configuration.slippage, "bid"),
                    price(ask + configuration.slippage, "ask"),
                    Quantity(1_000_000, size_precision),
                    Quantity(1_000_000, size_precision),
                    timestamp,
                    timestamp,
                )
            )
        basis = "OBSERVED_BID_ASK_TICKS"
    else:
        # Native orders replay a declared adverse-first path; not fabricated observed ticks.
        width = configuration.spread / 2 + configuration.slippage
        for index, candle in enumerate(candles):
            path = (
                (candle.open, candle.low, candle.high, candle.close)
                if direction == "LONG"
                else (candle.open, candle.high, candle.low, candle.close)
            )
            for part, mid in enumerate(path):
                timestamp = bar_times[index] + (timeframe_seconds * 1_000_000_000 - 1) * part // 3
                data.append(
                    QuoteTick(
                        instrument_id,
                        price(mid - width, "bid"),
                        price(mid + width, "ask"),
                        Quantity(1_000_000, size_precision),
                        Quantity(1_000_000, size_precision),
                        timestamp,
                        timestamp,
                    )
                )
        basis = "ASSUMED_OHLC_ADVERSE_FIRST_WITH_CONFIGURED_SPREAD"
    if not data:
        raise ValueError("no quotes available for execution validation")
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    replay = Replay()
    try:
        engine.add_venue(
            venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(configuration.initial_equity, currency)],
            base_currency=currency,
            default_leverage=Decimal(100),
            book_type=BookType.L1_MBP,
            fill_model=FillModel(prob_slippage=0, random_seed=7),
            fee_model=PerUnitFee(),
            use_message_queue=False,
        )
        engine.add_instrument(instrument)
        engine.add_strategy(replay)
        engine.add_data(data)
        engine.run()
        open_positions = engine.cache.positions_open(instrument_id=instrument_id)
        net = sum(Decimal(position["net_pnl"]) for position in replay.closed_positions)
        count = len(replay.closed_positions)
        average_r = sum(replay.closed_r) / count if count else 0
        return {
            "engine": "NautilusTrader",
            "version": nautilus_trader.__version__,
            "status": "COMPLETED",
            "passed": count >= 2
            and net > 0
            and average_r > 0
            and not replay.rejections
            and not open_positions
            and replay.max_drawdown <= configuration.max_total_loss,
            "trade_count": count,
            "net_pnl": str(net),
            "average_r": average_r,
            "intrabar_max_drawdown": str(replay.max_drawdown),
            "policy_passed": replay.max_drawdown <= configuration.max_total_loss,
            "data_basis": basis,
            "fills": replay.fills,
            "closed_positions": replay.closed_positions,
            "rejections": replay.rejections,
            "open_position_count": len(open_positions),
            "execution_authorized": False,
            "broker_specification_id": strategy.specification_version_id,
            "risk_basis": (
                "SIMULATION_IN_QUOTE_CURRENCY; AUTHORITATIVE_ACCOUNT_RISK_RECHECK_REQUIRED"
            ),
            "limitations": [
                "L1 liquidity assumed; queue, swaps and order-book impact unverified",
                "OHLC intrabar path is a model unless observed bid/ask ticks supplied",
            ],
        }
    finally:
        engine.dispose()
