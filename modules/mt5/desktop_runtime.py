"""Start and verify the host Wine/MetaTrader terminal before login sessions."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from packages.shared.config import Settings, get_settings


class MT5StartupError(RuntimeError):
    """The configured local Wine/MT5 runtime could not be started."""


@dataclass(frozen=True)
class MT5StartupResult:
    status: str
    wine_started: bool = False
    terminal_started: bool = False
    detail: str = ""


class MT5DesktopRuntime:
    """Idempotently start a configured terminal without invoking a shell.

    The API may run without a desktop terminal, so an unset terminal path is
    treated as ``not_configured``. Once a path is configured, startup is a
    session gate: a session is not persisted until the terminal process is
    visible and alive.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._terminal_process: subprocess.Popen[bytes] | None = None

    async def ensure_started(self, settings: Settings | None = None) -> MT5StartupResult:
        settings = settings or get_settings()
        if not settings.mt5_auto_start_enabled:
            return MT5StartupResult("disabled", detail="MT5 desktop autostart is disabled")
        configured_path = settings.mt5_terminal_path
        if configured_path is None:
            return MT5StartupResult(
                "not_configured",
                detail="MATRADES_MT5_TERMINAL_PATH is not configured",
            )

        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            return await self._ensure_started(settings, configured_path)

    async def _ensure_started(self, settings: Settings, configured_path: Path) -> MT5StartupResult:
        terminal_path = configured_path.expanduser().resolve()
        if not terminal_path.is_file():
            raise MT5StartupError("configured MT5 terminal executable was not found")

        wine_binary = self._resolve_binary(settings.mt5_wine_binary)
        if wine_binary is None:
            raise MT5StartupError("configured Wine executable was not found")

        if self._process_alive(self._terminal_process, terminal_path):
            return MT5StartupResult("ready", detail="MT5 terminal is already running")

        wine_started = False
        if not self._process_matches("wineserver"):
            wineboot_binary = self._resolve_binary(settings.mt5_wineboot_binary)
            if wineboot_binary is not None:
                await self._run_wineboot(wineboot_binary, settings, terminal_path)
                wine_started = True

        try:
            self._terminal_process = subprocess.Popen(
                [wine_binary, str(terminal_path)],
                cwd=str(terminal_path.parent),
                env=self._environment(settings),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise MT5StartupError("Wine could not launch the MT5 terminal") from exc

        deadline = asyncio.get_running_loop().time() + settings.mt5_startup_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if self._process_alive(self._terminal_process, terminal_path):
                return MT5StartupResult(
                    "ready",
                    wine_started=wine_started,
                    terminal_started=True,
                    detail="Wine and MT5 terminal are running",
                )
            await asyncio.sleep(0.25)

        if self._terminal_process.poll() is not None:
            raise MT5StartupError("MT5 terminal exited during startup")
        raise MT5StartupError("MT5 terminal did not become ready before the startup timeout")

    async def _run_wineboot(
        self, wineboot_binary: str, settings: Settings, terminal_path: Path
    ) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                wineboot_binary,
                "--init",
                cwd=str(terminal_path.parent),
                env=self._environment(settings),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=settings.mt5_startup_timeout_seconds)
        except (OSError, TimeoutError) as exc:
            raise MT5StartupError("Wine could not initialize its prefix") from exc
        if process.returncode != 0:
            raise MT5StartupError("Wine prefix initialization failed")

    @staticmethod
    def _resolve_binary(binary: str) -> str | None:
        candidate = Path(binary).expanduser()
        if candidate.parent != Path("."):
            return str(candidate) if candidate.is_file() else None
        return shutil.which(binary)

    @staticmethod
    def _environment(settings: Settings) -> dict[str, str]:
        environment = os.environ.copy()
        if settings.mt5_wine_prefix is not None:
            environment["WINEPREFIX"] = str(settings.mt5_wine_prefix.expanduser())
        return environment

    def _process_alive(self, process: subprocess.Popen[bytes] | None, terminal_path: Path) -> bool:
        if process is not None and process.poll() is None:
            return True
        return self._process_matches(str(terminal_path)) or self._process_matches(
            terminal_path.name
        )

    @staticmethod
    def _process_matches(token: str) -> bool:
        ps_binary = shutil.which("ps")
        if ps_binary is None:
            return False
        try:
            result = subprocess.run(
                [ps_binary, "-ax", "-o", "command="],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return any(token in line for line in result.stdout.splitlines())


_runtime = MT5DesktopRuntime()


async def ensure_mt5_started() -> MT5StartupResult:
    settings = get_settings()
    if settings.mt5_runtime_control_url:
        return await _ensure_remote_started(settings)
    return await _runtime.ensure_started(settings)


async def ensure_local_mt5_started(settings: Settings | None = None) -> MT5StartupResult:
    """Start the Wine/MT5 process on the machine running this service."""

    return await _runtime.ensure_started(settings or get_settings())


async def _ensure_remote_started(settings: Settings) -> MT5StartupResult:
    control_url = settings.mt5_runtime_control_url
    if not control_url:
        raise MT5StartupError("remote MT5 runtime control URL is not configured")
    token = (
        settings.mt5_runtime_control_token.get_secret_value()
        if settings.mt5_runtime_control_token is not None
        else ""
    )
    if not token:
        raise MT5StartupError("remote MT5 runtime control token is not configured")
    try:
        async with httpx.AsyncClient(
            timeout=settings.mt5_startup_timeout_seconds + 5
        ) as client:
            response = await client.post(
                control_url,
                headers={"X-Matrades-MT5-Runtime-Token": token},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MT5StartupError("remote MT5 runtime controller is unavailable") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        raise MT5StartupError("remote MT5 runtime did not become ready")
    return MT5StartupResult(
        "ready",
        wine_started=bool(payload.get("wine_started")),
        terminal_started=bool(payload.get("terminal_started")),
        detail="remote Wine and MT5 runtime is ready",
    )


def reset_runtime_for_tests() -> None:
    """Reset process bookkeeping without terminating a user-owned terminal."""

    _runtime._terminal_process = None
    _runtime._lock = None


__all__ = [
    "MT5DesktopRuntime",
    "MT5StartupError",
    "MT5StartupResult",
    "ensure_mt5_started",
    "ensure_local_mt5_started",
    "reset_runtime_for_tests",
]
