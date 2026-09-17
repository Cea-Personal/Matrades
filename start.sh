#!/usr/bin/env bash
set -Eeuo pipefail

# Railway provides PORT for the one public HTTP service port. Start the HTTP
# gateway before Xvfb and Wine so display initialization cannot cause a 502.

export WINEPREFIX="${MATRADES_MT5_WINE_PREFIX:-${WINEPREFIX:-/opt/wineprefix}}"
export WINEARCH="${WINEARCH:-win64}"
WINE_BIN="${MATRADES_MT5_WINE_BINARY:-wine}"
WINEBOOT_BIN="${MATRADES_MT5_WINEBOOT_BINARY:-wineboot}"
TERMINAL_PATH="${MATRADES_MT5_TERMINAL_PATH:-$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe}"
export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"
INSTALLER_PATH="${MT5_INSTALLER_PATH:-/app/mt5setup.exe}"
PUBLIC_PORT="${PORT:-8765}"
BRIDGE_PORT=18765
STATUS_PATH="${MATRADES_MT5_RUNTIME_STATUS_PATH:-/tmp/matrades-mt5-runtime.status}"
export DISPLAY=:99

echo "MT5 service starting (public port: $PUBLIC_PORT, bridge port: $BRIDGE_PORT)"

if [[ ! "$PUBLIC_PORT" =~ ^[0-9]+$ ]] || (( PUBLIC_PORT < 1 || PUBLIC_PORT > 65535 )); then
    echo "PORT must be a TCP port number between 1 and 65535" >&2
    exit 1
fi
if (( PUBLIC_PORT == BRIDGE_PORT || PUBLIC_PORT == 6080 || PUBLIC_PORT == 5900 )); then
    echo "PORT conflicts with an internal MT5 desktop port" >&2
    exit 1
fi
if [[ ! "${MATRADES_MT5_DESKTOP_USER:-}" =~ ^[A-Za-z0-9_.-]+$ ]] || [[ -z "${MATRADES_MT5_DESKTOP_PASSWORD:-}" ]]; then
    echo "Set MATRADES_MT5_DESKTOP_USER and MATRADES_MT5_DESKTOP_PASSWORD on the MT5 Railway service before exposing its desktop" >&2
    exit 1
fi
if [[ "$MATRADES_MT5_DESKTOP_PASSWORD" == *$'\n'* || "$MATRADES_MT5_DESKTOP_PASSWORD" == *$'\r'* ]]; then
    echo "MATRADES_MT5_DESKTOP_PASSWORD must not contain a newline" >&2
    exit 1
fi

umask 077
printf '%s\n' "$MATRADES_MT5_DESKTOP_PASSWORD" | htpasswd -i -c -5 /tmp/matrades-mt5-desktop.htpasswd "$MATRADES_MT5_DESKTOP_USER" >/dev/null
sed "s/__PORT__/$PUBLIC_PORT/" /app/bridges/mt5/nginx.conf.template > /tmp/matrades-mt5-nginx.conf
nginx -t -c /tmp/matrades-mt5-nginx.conf

set_status() {
    printf '%s\n' "$1" > "$STATUS_PATH"
}

fail_and_serve() {
    set_status "$1"
    echo "MT5 startup failed ($1); the desktop and /status remain available for diagnosis" >&2
    wait "$NGINX_PID"
    exit 1
}

mkdir -p "$(dirname "$STATUS_PATH")"
set_status starting
echo "Starting MT5 desktop gateway on port $PUBLIC_PORT and bridge on loopback port $BRIDGE_PORT"
uvicorn bridges.mt5.app:app --host 127.0.0.1 --port "$BRIDGE_PORT" &
BRIDGE_PID=$!
nginx -c /tmp/matrades-mt5-nginx.conf -g 'daemon off;' &
NGINX_PID=$!
sleep 2
for service_pid in "$BRIDGE_PID" "$NGINX_PID"; do
    if ! kill -0 "$service_pid" 2>/dev/null; then
        echo "The MT5 HTTP gateway or bridge exited during startup" >&2
        exit 1
    fi
done
echo "MT5 HTTP gateway is running on port $PUBLIC_PORT"

set_status initializing_display
echo "Starting Xvfb display $DISPLAY"
Xvfb "$DISPLAY" -screen 0 1024x768x24 -ac -nolisten tcp +extension GLX +render -noreset >/tmp/matrades-xvfb.log 2>&1 &
XVFB_PID=$!
for attempt in {1..40}; do
    if [[ -S /tmp/.X11-unix/X99 ]] && kill -0 "$XVFB_PID" 2>/dev/null; then
        break
    fi
    sleep 0.25
done
if [[ ! -S /tmp/.X11-unix/X99 ]] || ! kill -0 "$XVFB_PID" 2>/dev/null; then
    echo "Xvfb did not start; recent display log:" >&2
    tail -n 60 /tmp/matrades-xvfb.log >&2
    fail_and_serve display_failed
fi

fluxbox >/tmp/matrades-fluxbox.log 2>&1 &
x11vnc -display "$DISPLAY" -rfbport 5900 -localhost -forever -shared -nopw -quiet >/tmp/matrades-x11vnc.log 2>&1 &
VNC_PID=$!
websockify 127.0.0.1:6080 127.0.0.1:5900 >/tmp/matrades-websockify.log 2>&1 &
WEBSOCKIFY_PID=$!
sleep 2
for service_pid in "$VNC_PID" "$WEBSOCKIFY_PID"; do
    if ! kill -0 "$service_pid" 2>/dev/null; then
        echo "An MT5 desktop service exited during startup" >&2
        tail -n 30 /tmp/matrades-x11vnc.log /tmp/matrades-websockify.log >&2
        fail_and_serve display_failed
    fi
done
echo "MT5 browser desktop is ready; initializing Wine"

mkdir -p "$WINEPREFIX"
set_status initializing_wine
echo "Initializing Wine prefix at $WINEPREFIX (display: $DISPLAY, host architecture: $(uname -m), image architecture: $(dpkg --print-architecture))"
if ! timeout 300s "$WINEBOOT_BIN" --init || ! timeout 30s "$WINE_BIN" cmd /c ver; then
    echo "Wine failed to initialize the configured prefix. Testing a temporary prefix to isolate the volume." >&2
    PROBE_PREFIX="$(mktemp -d /tmp/matrades-wine-probe.XXXXXX)"
    PROBE_LOG="$(mktemp /tmp/matrades-wine-probe-log.XXXXXX)"
    if {
        WINEPREFIX="$PROBE_PREFIX" WINEDEBUG=+loaddll timeout 300s "$WINEBOOT_BIN" --init &&
            WINEPREFIX="$PROBE_PREFIX" timeout 30s "$WINE_BIN" cmd /c ver
    } >"$PROBE_LOG" 2>&1; then
        echo "Wine works with a temporary prefix. The configured prefix or volume is the likely cause; use a new prefix directory on the existing volume." >&2
    else
        echo "Last 80 lines of Wine loader diagnostics:" >&2
        tail -n 80 "$PROBE_LOG" >&2
        echo "Wine also fails with a temporary prefix. Check the Wine image and Railway runtime logs; changing the volume will not fix this." >&2
    fi
    fail_and_serve wine_failed
fi

if [[ ! -f "$TERMINAL_PATH" ]]; then
    if [[ ! -f "$INSTALLER_PATH" && -n "${MT5_INSTALLER_URL:-}" ]]; then
        echo "Downloading MetaTrader 5 installer"
        if ! curl -fsSL "$MT5_INSTALLER_URL" -o "$INSTALLER_PATH"; then
            fail_and_serve installer_download_failed
        fi
    fi
    if [[ ! -f "$INSTALLER_PATH" ]]; then
        echo "MT5 terminal is missing and installer was not found at $INSTALLER_PATH" >&2
        fail_and_serve installer_missing
    fi
    set_status installing_mt5
    echo "Installing MetaTrader 5 from $INSTALLER_PATH"
    if ! "$WINE_BIN" "$INSTALLER_PATH" /s; then
        fail_and_serve installer_failed
    fi
    sleep 10
fi

if [[ ! -f "$TERMINAL_PATH" ]]; then
    TERMINAL_PATH="$(find "$WINEPREFIX/drive_c" -type f -iname terminal64.exe -print -quit)"
    export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"
fi
if [[ -z "$TERMINAL_PATH" || ! -f "$TERMINAL_PATH" ]]; then
    echo "MetaTrader 5 terminal64.exe was not found after installation" >&2
    fail_and_serve terminal_missing
fi

set_status starting_terminal
echo "Starting MT5 terminal: $TERMINAL_PATH"
"$WINE_BIN" "$TERMINAL_PATH" >/tmp/mt5.log 2>&1 &
MT5_PID=$!
sleep 2
if ! kill -0 "$MT5_PID" 2>/dev/null && ! pgrep -f -- "$TERMINAL_PATH" >/dev/null; then
    echo "MT5 terminal exited immediately; recent terminal log:" >&2
    tail -n 60 /tmp/mt5.log >&2
    fail_and_serve terminal_failed
fi
set_status terminal_started

while kill -0 "$BRIDGE_PID" 2>/dev/null && kill -0 "$NGINX_PID" 2>/dev/null && kill -0 "$XVFB_PID" 2>/dev/null && kill -0 "$VNC_PID" 2>/dev/null && kill -0 "$WEBSOCKIFY_PID" 2>/dev/null; do
    if ! kill -0 "$MT5_PID" 2>/dev/null; then
        echo "MT5 terminal exited; restarting it" >&2
        set_status starting_terminal
        "$WINE_BIN" "$TERMINAL_PATH" >/tmp/mt5.log 2>&1 &
        MT5_PID=$!
        sleep 2
        if ! kill -0 "$MT5_PID" 2>/dev/null && ! pgrep -f -- "$TERMINAL_PATH" >/dev/null; then
            echo "MT5 terminal failed after restart; recent terminal log:" >&2
            tail -n 60 /tmp/mt5.log >&2
            fail_and_serve terminal_failed
        fi
        set_status terminal_started
    fi
    sleep 5
done

echo "The MT5 desktop gateway or bridge stopped unexpectedly" >&2
exit 1
