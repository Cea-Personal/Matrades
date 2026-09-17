from pathlib import Path
from types import SimpleNamespace

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
