import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from modules.mt5.desktop_runtime import MT5DesktopRuntime, MT5StartupError


@pytest.mark.asyncio
async def test_autostart_is_a_safe_noop_without_terminal_path():
    settings = SimpleNamespace(mt5_auto_start_enabled=True, mt5_terminal_path=None)
    result = await MT5DesktopRuntime().ensure_started(settings)
    assert result.status == "not_configured"


@pytest.mark.asyncio
async def test_configured_missing_terminal_fails_before_session_creation(tmp_path: Path):
    settings = SimpleNamespace(
        mt5_auto_start_enabled=True,
        mt5_terminal_path=tmp_path / "terminal64.exe",
    )
    with pytest.raises(MT5StartupError, match="not found"):
        await MT5DesktopRuntime().ensure_started(settings)


@pytest.mark.asyncio
async def test_disabled_autostart_does_not_require_terminal_path():
    settings = SimpleNamespace(mt5_auto_start_enabled=False, mt5_terminal_path=None)
    result = await MT5DesktopRuntime().ensure_started(settings)
    assert result.status == "disabled"


def configured_settings(tmp_path: Path):
    terminal = tmp_path / "terminal64.exe"
    terminal.touch()
    return SimpleNamespace(
        mt5_auto_start_enabled=True,
        mt5_terminal_path=terminal,
        mt5_wine_binary="wine",
        mt5_wineboot_binary="wineboot",
        mt5_startup_timeout_seconds=3,
        mt5_wine_prefix=None,
    )


async def test_parallel_startup_requests_launch_only_one_terminal(tmp_path, monkeypatch):
    runtime = MT5DesktopRuntime()
    settings = configured_settings(tmp_path)
    process = Mock()
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr(runtime, "_resolve_binary", lambda name: f"/resolved/{name}")
    monkeypatch.setattr(runtime, "_process_matches", lambda command: command == "wineserver")
    monkeypatch.setattr(runtime, "_launch_terminal", launch)
    results = await asyncio.gather(
        runtime.ensure_started(settings), runtime.ensure_started(settings)
    )
    assert [result.status for result in results] == ["ready", "ready"]
    assert sum(result.terminal_started for result in results) == 1
    assert not any(result.wine_started for result in results)
    launch.assert_called_once_with("/resolved/wine", settings.mt5_terminal_path, settings)


async def test_running_user_owned_terminal_is_not_relaunched(tmp_path, monkeypatch):
    runtime = MT5DesktopRuntime()
    settings = configured_settings(tmp_path)
    launch = Mock()
    monkeypatch.setattr(runtime, "_resolve_binary", lambda name: f"/resolved/{name}")
    monkeypatch.setattr(runtime, "_process_matches", lambda command: "terminal64.exe" in command)
    monkeypatch.setattr(runtime, "_launch_terminal", launch)
    result = await runtime.ensure_started(settings)
    assert result.status == "ready"
    assert not result.terminal_started
    launch.assert_not_called()


async def test_wineboot_failure_still_blocks_terminal_launch(tmp_path, monkeypatch):
    runtime = MT5DesktopRuntime()
    launch = Mock()
    boot = AsyncMock(side_effect=MT5StartupError("Wine prefix initialization failed"))
    monkeypatch.setattr(runtime, "_resolve_binary", lambda name: f"/resolved/{name}")
    monkeypatch.setattr(runtime, "_process_matches", lambda command: False)
    monkeypatch.setattr(runtime, "_run_wineboot", boot)
    monkeypatch.setattr(runtime, "_launch_terminal", launch)
    with pytest.raises(MT5StartupError, match="initialization failed"):
        await runtime.ensure_started(configured_settings(tmp_path))
    boot.assert_awaited_once()
    launch.assert_not_called()


async def test_launch_os_error_remains_a_controlled_startup_failure(tmp_path, monkeypatch):
    runtime = MT5DesktopRuntime()
    monkeypatch.setattr(runtime, "_resolve_binary", lambda name: f"/resolved/{name}")
    monkeypatch.setattr(runtime, "_process_matches", lambda command: command == "wineserver")
    monkeypatch.setattr(runtime, "_launch_terminal", Mock(side_effect=OSError("launch failure")))
    with pytest.raises(MT5StartupError, match="could not launch"):
        await runtime.ensure_started(configured_settings(tmp_path))
