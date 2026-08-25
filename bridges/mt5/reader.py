from __future__ import annotations

from typing import Any, Protocol


class Mt5ReadApi(Protocol):
    def account_info(self) -> Any: ...
    def positions_get(self) -> Any: ...
    def orders_get(self) -> Any: ...
    def history_deals_get(self, *args: Any) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...

    def symbols_get(self) -> Any: ...


class Mt5Reader:
    def __init__(self, api: Mt5ReadApi) -> None:
        self.api = api

    def account(self) -> Any:
        return self.api.account_info()

    def positions(self) -> Any:
        return self.api.positions_get() or ()

    def orders(self) -> Any:
        return self.api.orders_get() or ()

    def history(self, *window: Any) -> Any:
        return self.api.history_deals_get(*window) or ()

    def symbol(self, symbol: str) -> Any:
        return self.api.symbol_info(symbol)

    def symbols(self) -> Any:
        getter = getattr(self.api, "symbols_get", None)
        return getter() if getter else ()

    def symbol_details(self, symbol: str) -> dict[str, Any]:
        """Normalize common MetaTrader symbol terms without converting types."""
        info = self.symbol(symbol)
        if isinstance(info, dict):
            return {str(key): value for key, value in info.items()}
        fields = (
            "name",
            "path",
            "description",
            "trade_contract_size",
            "trade_tick_size",
            "trade_tick_value",
            "volume_min",
            "volume_max",
            "volume_step",
            "swap_long",
            "swap_short",
            "expiration_time",
            "trade_mode",
        )
        return {field: getattr(info, field, None) for field in fields}
