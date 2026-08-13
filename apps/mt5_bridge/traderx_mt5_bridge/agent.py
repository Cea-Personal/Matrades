"""Outbound, read-only MT5 bridge agent for a TraderX-managed enrollment.

Run this beside a provisioned Windows MT5 terminal. The process initiates every connection to
TraderX over HTTPS; it has no listening socket and contains no trading operation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from getpass import getpass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from traderx_mt5_bridge.app import (
    MetaTraderTerminalReader,
    Mt5TerminalConfiguration,
    TerminalReadError,
)


class BridgeAgentError(RuntimeError):
    """The managed bridge cannot safely provide a verified terminal snapshot."""


@dataclass(frozen=True, slots=True)
class BridgeConnection:
    api_base_url: str
    agent_id: str
    agent_token: str
    login: str
    server: str


class TraderXBridgeClient:
    """A tiny outbound-only HTTP client with a fixed enrollment/snapshot allowlist."""

    def __init__(self, api_base_url: str, agent_id: UUID) -> None:
        if not api_base_url.startswith("https://"):
            raise BridgeAgentError("TraderX must be addressed by an HTTPS URL")
        self._api_base_url = api_base_url.rstrip("/")
        self._agent_id = str(agent_id)

    def enrollment_configuration(self, enrollment_code: str) -> dict[str, str]:
        result = self._post("configuration", {"enrollment_code": enrollment_code})
        return self._identity(result)

    def enroll(self, enrollment_code: str, state: object) -> str:
        result = self._post(
            "enroll",
            {"enrollment_code": enrollment_code, **_terminal_payload(state)},
        )
        token = result.get("agent_token")
        if not isinstance(token, str) or not token:
            raise BridgeAgentError("TraderX did not return a bridge credential")
        return token

    def send_snapshot(self, connection: BridgeConnection, state: object, snapshot: object) -> None:
        payload = {**_terminal_payload(state), **asdict(snapshot)}
        self._post("snapshots", payload, agent_token=connection.agent_token)

    def _post(
        self, operation: str, payload: dict[str, object], *, agent_token: str | None = None
    ) -> dict[str, object]:
        allowed = {"configuration", "enroll", "snapshots"}
        if operation not in allowed:
            raise BridgeAgentError("the requested bridge operation is not permitted")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if agent_token is not None:
            headers["Authorization"] = f"Bearer {agent_token}"
        request = Request(  # noqa: S310 - URL is validated as HTTPS at construction
            f"{self._api_base_url}/integrations/mt5/agents/{self._agent_id}/{operation}",
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed HTTPS operator URL
                body = response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            raise BridgeAgentError("TraderX did not accept the read-only bridge evidence") from error
        try:
            result: Any = json.loads(body)
        except json.JSONDecodeError as error:
            raise BridgeAgentError("TraderX returned an invalid bridge response") from error
        if not isinstance(result, dict):
            raise BridgeAgentError("TraderX returned an invalid bridge response")
        return result

    @staticmethod
    def _identity(result: dict[str, object]) -> dict[str, str]:
        login = result.get("login")
        server = result.get("server")
        if not isinstance(login, str) or not login or not isinstance(server, str) or not server:
            raise BridgeAgentError("TraderX returned an invalid MT5 enrollment identity")
        return {"login": login, "server": server}


def _terminal_payload(state: object) -> dict[str, object]:
    connected = bool(getattr(state, "connected", False))
    trading_disabled = not bool(getattr(state, "terminal_trade_allowed", True)) and not bool(
        getattr(state, "account_trade_allowed", True)
    )
    login = str(getattr(state, "login", ""))
    server = str(getattr(state, "server", ""))
    terminal_version = str(getattr(state, "terminal_version", ""))
    if not connected or not trading_disabled or not login or not server or not terminal_version:
        raise BridgeAgentError("MT5 must be connected with an investor password and trading disabled")
    return {
        "connected": connected,
        "trading_disabled": trading_disabled,
        "login": login,
        "server": server,
        "terminal_version": terminal_version,
    }


def _state_path() -> Path:
    app_data = Path(os.getenv("APPDATA", Path.home()))
    return app_data / "TraderX" / "mt5-bridge" / "connection.json"


def _load_connection(path: Path) -> BridgeConnection | None:
    if not path.exists():
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return BridgeConnection(
            api_base_url=_required_string(payload, "api_base_url"),
            agent_id=_required_string(payload, "agent_id"),
            agent_token=_required_string(payload, "agent_token"),
            login=_required_string(payload, "login"),
            server=_required_string(payload, "server"),
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _save_connection(path: Path, connection: BridgeConnection) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(connection), sort_keys=True), encoding="utf-8")
    with suppress(OSError):
        path.chmod(0o600)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {key}")
    return value


def _read_password() -> str:
    value = os.getenv("TRADERX_MT5_INVESTOR_PASSWORD") or getpass("MT5 investor password: ")
    if not value:
        raise BridgeAgentError("an MT5 investor password is required on this Windows host")
    return value


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TraderX's read-only outbound MT5 bridge")
    parser.add_argument("--api-url", required=True, help="TraderX public origin followed by /api/v1")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--enrollment-code", help="One-time code from Command Center; required first run")
    parser.add_argument(
        "--terminal-path",
        default=r"C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        help="Path to the broker's installed MT5 terminal64.exe",
    )
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--once", action="store_true", help="Send one snapshot then exit")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if not arguments.api_url.startswith("https://"):
        raise BridgeAgentError("TraderX must be addressed by an HTTPS URL")
    if arguments.interval_seconds < 5:
        raise BridgeAgentError("the bridge interval must be at least five seconds")
    agent_id = UUID(arguments.agent_id)
    state_path = _state_path()
    connection = _load_connection(state_path)
    reader: MetaTraderTerminalReader | None = None
    if connection is not None and (
        connection.api_base_url != arguments.api_url.rstrip("/") or connection.agent_id != str(agent_id)
    ):
        raise BridgeAgentError("the saved bridge connection belongs to a different TraderX enrollment")

    try:
        if connection is None:
            if not arguments.enrollment_code:
                raise BridgeAgentError(
                    "a one-time enrollment code is required the first time the bridge runs"
                )
            client = TraderXBridgeClient(arguments.api_url, agent_id)
            identity = client.enrollment_configuration(arguments.enrollment_code)
            reader = MetaTraderTerminalReader(
                Mt5TerminalConfiguration(
                    terminal_path=arguments.terminal_path,
                    login=identity["login"],
                    investor_password=_read_password(),
                    server=identity["server"],
                )
            )
            state = reader.state()
            agent_token = client.enroll(arguments.enrollment_code, state)
            connection = BridgeConnection(
                api_base_url=arguments.api_url.rstrip("/"),
                agent_id=str(agent_id),
                agent_token=agent_token,
                login=identity["login"],
                server=identity["server"],
            )
            _save_connection(state_path, connection)

        if reader is None:
            reader = MetaTraderTerminalReader(
                Mt5TerminalConfiguration(
                    terminal_path=arguments.terminal_path,
                    login=connection.login,
                    investor_password=_read_password(),
                    server=connection.server,
                )
            )
        client = TraderXBridgeClient(connection.api_base_url, agent_id)
        while True:
            state = reader.state()
            snapshot = reader.snapshot()
            client.send_snapshot(connection, state, snapshot)
            print("TraderX accepted a verified MT5 read-only snapshot.", flush=True)
            if arguments.once:
                return 0
            time.sleep(arguments.interval_seconds)
    except TerminalReadError as error:
        raise BridgeAgentError("MT5 did not provide a complete read-only terminal snapshot") from error
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BridgeAgentError as error:
        print(f"TraderX MT5 bridge stopped: {error}", file=sys.stderr)
        raise SystemExit(1) from error
