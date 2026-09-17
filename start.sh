#!/usr/bin/env bash
set -Eeuo pipefail

# Railway provides PORT for the one public HTTP service port. The bridge exposes
# /runtime/start and the existing signed MT5 bridge endpoints on that port.
export WINEPREFIX="${MATRADES_MT5_WINE_PREFIX:-${WINEPREFIX:-/opt/wineprefix}}"
export DISPLAY="${DISPLAY:-:99}"
WINE_BIN="${MATRADES_MT5_WINE_BINARY:-wine}"
WINEBOOT_BIN="${MATRADES_MT5_WINEBOOT_BINARY:-wineboot}"
TERMINAL_PATH="${MATRADES_MT5_TERMINAL_PATH:-$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe}"
INSTALLER_PATH="${MT5_INSTALLER_PATH:-/app/mt5setup.exe}"
BRIDGE_PORT="${PORT:-8765}"

mkdir -p "$WINEPREFIX"
Xvfb "$DISPLAY" -screen 0 1024x768x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
sleep 2

"$WINEBOOT_BIN" -u

if [[ ! -f "$TERMINAL_PATH" ]]; then
    if [[ ! -f "$INSTALLER_PATH" && -n "${MT5_INSTALLER_URL:-}" ]]; then
        echo "Downloading MetaTrader 5 installer"
        curl -fsSL "$MT5_INSTALLER_URL" -o "$INSTALLER_PATH"
    fi
    if [[ ! -f "$INSTALLER_PATH" ]]; then
        echo "MT5 terminal is missing and installer was not found at $INSTALLER_PATH" >&2
        exit 1
    fi
    echo "Installing MetaTrader 5 from $INSTALLER_PATH"
    "$WINE_BIN" "$INSTALLER_PATH" /s
    sleep 10
fi

if [[ ! -f "$TERMINAL_PATH" ]]; then
    TERMINAL_PATH="$(find "$WINEPREFIX/drive_c" -type f -iname terminal64.exe -print -quit)"
fi
if [[ -z "$TERMINAL_PATH" || ! -f "$TERMINAL_PATH" ]]; then
    echo "MetaTrader 5 terminal64.exe was not found after installation" >&2
    exit 1
fi

echo "Starting MT5 terminal: $TERMINAL_PATH"
"$WINE_BIN" "$TERMINAL_PATH" >/tmp/mt5.log 2>&1 &
MT5_PID=$!

echo "Starting Matrades MT5 bridge on port $BRIDGE_PORT"
uvicorn bridges.mt5.app:app --host 0.0.0.0 --port "$BRIDGE_PORT" &
BRIDGE_PID=$!

while kill -0 "$BRIDGE_PID" 2>/dev/null; do
    if ! kill -0 "$MT5_PID" 2>/dev/null; then
        echo "MT5 terminal exited; restarting it" >&2
        "$WINE_BIN" "$TERMINAL_PATH" >/tmp/mt5.log 2>&1 &
        MT5_PID=$!
    fi
    sleep 5
done

wait "$BRIDGE_PID"
