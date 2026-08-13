from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException


@dataclass(frozen=True, slots=True)
class TerminalState:
    connected: bool
    terminal_trade_allowed: bool
    account_trade_allowed: bool
    login: str
    server: str
    terminal_version: str


@dataclass(frozen=True, slots=True)
class BridgeSnapshot:
    balance: str
    equity: str
    currency: str
    positions: list[dict[str, object]]
    deals: list[dict[str, object]]
    instruments: list[dict[str, object]]


class TerminalReader(Protocol):
    def state(self) -> TerminalState: ...

    def snapshot(self) -> BridgeSnapshot: ...


class TerminalReadError(RuntimeError):
    """MT5 terminal IPC did not yield a complete, read-only account view."""


@dataclass(frozen=True, slots=True)
class Mt5TerminalConfiguration:
    terminal_path: str
    login: str
    investor_password: str
    server: str
    timeout_milliseconds: int = 10_000


class MetaTraderTerminalReader:
    """A local-only MetaTrader5 IPC reader used within the isolated bridge.

    `investor_password` is held only by this process. The allowlist below intentionally contains
    no order, calculation, script, or terminal-state mutation functions.
    """

    def __init__(self, configuration: Mt5TerminalConfiguration, mt5_module: Any | None = None) -> None:
        self._configuration = configuration
        self._mt5 = mt5_module

    def state(self) -> TerminalState:
        mt5 = self._client()
        if not mt5.initialize(
            path=self._configuration.terminal_path,
            login=int(self._configuration.login),
            password=self._configuration.investor_password,
            server=self._configuration.server,
            timeout=self._configuration.timeout_milliseconds,
        ):
            raise TerminalReadError(self._last_error(mt5))
        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()
        if terminal_info is None or account_info is None:
            raise TerminalReadError(self._last_error(mt5))
        version = mt5.version()
        return TerminalState(
            connected=bool(terminal_info.connected),
            terminal_trade_allowed=bool(terminal_info.trade_allowed),
            account_trade_allowed=bool(account_info.trade_allowed),
            login=str(account_info.login),
            server=str(account_info.server),
            terminal_version=".".join(str(part) for part in version),
        )

    def snapshot(self) -> BridgeSnapshot:
        mt5 = self._client()
        account_info = mt5.account_info()
        positions = mt5.positions_get()
        # A bounded overlapping lookback is reconciled by TraderX; it is never a fabricated cursor.
        deals = mt5.history_deals_get(datetime.now(UTC) - timedelta(days=2), datetime.now(UTC))
        instruments = mt5.symbols_get()
        if any(value is None for value in (account_info, positions, deals, instruments)):
            raise TerminalReadError(self._last_error(mt5))
        return BridgeSnapshot(
            balance=str(account_info.balance),
            equity=str(account_info.equity),
            currency=str(account_info.currency),
            positions=[self._record(item) for item in positions],
            deals=[self._record(item) for item in deals],
            instruments=[self._record(item) for item in instruments],
        )

    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def _client(self) -> Any:
        if self._mt5 is None:
            try:
                self._mt5 = import_module("MetaTrader5")
            except ModuleNotFoundError as error:
                raise TerminalReadError("MetaTrader5 is not installed on this bridge host") from error
        return self._mt5

    @staticmethod
    def _record(item: Any) -> dict[str, object]:
        values = item._asdict() if hasattr(item, "_asdict") else vars(item)
        return {str(key): str(value) if isinstance(value, float) else value for key, value in values.items()}

    @staticmethod
    def _last_error(mt5: Any) -> str:
        code, message = mt5.last_error()
        return f"MT5 IPC error {code}: {message}"


def _verified_state(
    reader: TerminalReader, *, expected_login: str, expected_server: str
) -> TerminalState:
    state = reader.state()
    if not state.connected:
        raise HTTPException(status_code=503, detail="MT5 terminal is disconnected")
    if state.login != expected_login or state.server != expected_server:
        raise HTTPException(status_code=503, detail="MT5 terminal account identity does not match")
    if state.terminal_trade_allowed or state.account_trade_allowed:
        raise HTTPException(status_code=503, detail="MT5 trading must be disabled for the bridge")
    return state


def create_app(
    reader: TerminalReader, *, expected_login: str, expected_server: str
) -> FastAPI:
    """Build an API whose entire public surface is read-only terminal evidence."""

    app = FastAPI(title="TraderX MT5 Read-only Bridge", version="1.0.0")

    @app.get("/v1/health")
    def health() -> dict[str, object]:
        try:
            state = _verified_state(
                reader, expected_login=expected_login, expected_server=expected_server
            )
        except TerminalReadError as error:
            raise HTTPException(status_code=503, detail="MT5 terminal evidence is unavailable") from error
        return {
            "connected": state.connected,
            "trading_disabled": True,
            "login": state.login,
            "server": state.server,
            "terminal_version": state.terminal_version,
        }

    @app.get("/v1/account-snapshot")
    def account_snapshot() -> dict[str, object]:
        try:
            state = _verified_state(
                reader, expected_login=expected_login, expected_server=expected_server
            )
            snapshot = reader.snapshot()
        except TerminalReadError as error:
            raise HTTPException(status_code=503, detail="MT5 terminal evidence is unavailable") from error
        return {
            **asdict(snapshot),
            "login": state.login,
            "server": state.server,
            "terminal_version": state.terminal_version,
            "trading_disabled": True,
        }

    @app.get("/v1/positions")
    def positions() -> list[dict[str, object]]:
        try:
            _verified_state(reader, expected_login=expected_login, expected_server=expected_server)
            return reader.snapshot().positions
        except TerminalReadError as error:
            raise HTTPException(status_code=503, detail="MT5 terminal evidence is unavailable") from error

    @app.get("/v1/deals")
    def deals() -> list[dict[str, object]]:
        try:
            _verified_state(reader, expected_login=expected_login, expected_server=expected_server)
            return reader.snapshot().deals
        except TerminalReadError as error:
            raise HTTPException(status_code=503, detail="MT5 terminal evidence is unavailable") from error

    @app.get("/v1/instruments")
    def instruments() -> list[dict[str, object]]:
        try:
            _verified_state(reader, expected_login=expected_login, expected_server=expected_server)
            return reader.snapshot().instruments
        except TerminalReadError as error:
            raise HTTPException(status_code=503, detail="MT5 terminal evidence is unavailable") from error

    return app
