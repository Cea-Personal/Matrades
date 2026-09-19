#!/usr/bin/env bash

set -Eeuo pipefail

# =========================================================
# Configuration
# =========================================================

export DISPLAY="${DISPLAY:-:99}"
export WINEARCH="${WINEARCH:-win64}"
export WINEPREFIX="${MATRADES_MT5_WINE_PREFIX:-${WINEPREFIX:-/data/wineprefix}}"

WINE_BIN="${MATRADES_MT5_WINE_BINARY:-wine}"
WINEBOOT_BIN="${MATRADES_MT5_WINEBOOT_BINARY:-wineboot}"

PUBLIC_PORT="${PORT:-8080}"
BRIDGE_PORT="${MATRADES_MT5_BRIDGE_PORT:-18765}"

VNC_PORT=5900
NOVNC_PORT=6080

STATUS_PATH="${MATRADES_MT5_RUNTIME_STATUS_PATH:-/tmp/matrades-mt5-runtime.status}"

DEFAULT_TERMINAL_PATH="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"

TERMINAL_PATH="${MATRADES_MT5_TERMINAL_PATH:-$DEFAULT_TERMINAL_PATH}"

INSTALLER_PATH="${MT5_INSTALLER_PATH:-/app/mt5setup.exe}"

export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"


# =========================================================
# Helpers
# =========================================================

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}

set_status() {
    printf '%s\n' "$1" > "$STATUS_PATH"
    log "STATUS: $1"
}

fatal() {
    set_status "$1"
    log "FATAL: $1"
    exit 1
}

process_running() {
    kill -0 "$1" 2>/dev/null
}

mt5_running() {
    if [[ -n "${MT5_PID:-}" ]] && kill -0 "$MT5_PID" 2>/dev/null; then
        return 0
    fi

    pgrep -f 'terminal64\.exe' >/dev/null 2>&1
}


# =========================================================
# Validate configuration
# =========================================================

mkdir -p "$(dirname "$STATUS_PATH")"
set_status starting

log "Starting Matrades MT5 runtime"

log "Architecture:"
log "  kernel: $(uname -m)"
log "  Debian: $(dpkg --print-architecture)"
log "  foreign: $(dpkg --print-foreign-architectures || true)"

log "Wine:"
"$WINE_BIN" --version

if [[ ! "$PUBLIC_PORT" =~ ^[0-9]+$ ]]; then
    fatal invalid_public_port
fi

if [[ -z "${MATRADES_MT5_DESKTOP_USER:-}" ]]; then
    fatal desktop_username_missing
fi

if [[ -z "${MATRADES_MT5_DESKTOP_PASSWORD:-}" ]]; then
    fatal desktop_password_missing
fi


# =========================================================
# Persistent storage
# =========================================================

mkdir -p "$WINEPREFIX"

log "Wine prefix: $WINEPREFIX"


# =========================================================
# Start X display
# =========================================================

set_status starting_display

log "Starting Xvfb on $DISPLAY"

Xvfb "$DISPLAY" \
    -screen 0 1440x900x24 \
    -ac \
    -nolisten tcp \
    +extension GLX \
    +render \
    -noreset \
    >/tmp/xvfb.log 2>&1 &

XVFB_PID=$!

for attempt in $(seq 1 40); do

    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        break
    fi

    if ! process_running "$XVFB_PID"; then
        cat /tmp/xvfb.log
        fatal display_failed
    fi

    sleep 0.25

done

if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    cat /tmp/xvfb.log
    fatal display_failed
fi

log "X display ready"


# =========================================================
# Window manager
# =========================================================

fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!


# =========================================================
# VNC
# =========================================================

log "Starting VNC"

x11vnc \
    -display "$DISPLAY" \
    -rfbport "$VNC_PORT" \
    -localhost \
    -forever \
    -shared \
    -nopw \
    -quiet \
    >/tmp/x11vnc.log 2>&1 &

VNC_PID=$!


# =========================================================
# noVNC
# =========================================================

log "Starting noVNC"

websockify \
    --web=/usr/share/novnc \
    "127.0.0.1:${NOVNC_PORT}" \
    "127.0.0.1:${VNC_PORT}" \
    >/tmp/novnc.log 2>&1 &

NOVNC_PID=$!


# =========================================================
# Wine initialization
# =========================================================

set_status initializing_wine

log "Initializing Wine prefix"

if ! timeout 180s "$WINEBOOT_BIN" --init >/tmp/wineboot.log 2>&1; then

    log "wineboot failed"

    cat /tmp/wineboot.log

    fatal wineboot_failed

fi


log "Testing Wine"

if ! timeout 30s "$WINE_BIN" cmd /c echo WINE_OK >/tmp/winetest.log 2>&1; then

    log "Wine command test failed"

    cat /tmp/winetest.log

    fatal wine_test_failed

fi

log "Wine initialized successfully"


# =========================================================
# Find MT5
# =========================================================

if [[ ! -f "$TERMINAL_PATH" ]]; then

    log "Checking Wine prefix for terminal64.exe"

    FOUND_TERMINAL="$(
        find "$WINEPREFIX/drive_c" \
            -type f \
            -iname 'terminal64.exe' \
            -print \
            -quit 2>/dev/null || true
    )"

    if [[ -n "$FOUND_TERMINAL" ]]; then

        TERMINAL_PATH="$FOUND_TERMINAL"

        export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"

    fi
fi


# =========================================================
# MT5 installation/bootstrap
# =========================================================

if [[ ! -f "$TERMINAL_PATH" ]]; then

    set_status mt5_install_required

    log "MetaTrader 5 is not currently installed."
    log ""
    log "Wine and the remote desktop are working."
    log ""
    log "Install MT5 using the browser desktop."
    log ""

    if [[ -f "$INSTALLER_PATH" ]]; then

        log "Launching MT5 installer: $INSTALLER_PATH"

        "$WINE_BIN" "$INSTALLER_PATH" \
            >/tmp/mt5-installer.log 2>&1 &

    else

        log "No installer found at:"
        log "$INSTALLER_PATH"

    fi

fi


# =========================================================
# Bridge
# =========================================================

log "Starting Matrades MT5 bridge"

uvicorn bridges.mt5.app:app \
    --host 127.0.0.1 \
    --port "$BRIDGE_PORT" \
    >/tmp/bridge.log 2>&1 &

BRIDGE_PID=$!


# =========================================================
# Authentication for desktop
# =========================================================

umask 077

printf '%s\n' "$MATRADES_MT5_DESKTOP_PASSWORD" |
    htpasswd \
        -i \
        -c \
        -B \
        /tmp/matrades-mt5-desktop.htpasswd \
        "$MATRADES_MT5_DESKTOP_USER" \
        >/dev/null


# =========================================================
# nginx
# =========================================================

sed \
    "s/__PORT__/$PUBLIC_PORT/g" \
    /app/bridges/mt5/nginx.conf.template \
    > /tmp/matrades-mt5-nginx.conf

nginx -t -c /tmp/matrades-mt5-nginx.conf

log "Starting nginx on Railway port $PUBLIC_PORT"

nginx \
    -c /tmp/matrades-mt5-nginx.conf \
    -g 'daemon off;' \
    >/tmp/nginx.log 2>&1 &

NGINX_PID=$!


# =========================================================
# Start MT5
# =========================================================

start_mt5() {

    if [[ ! -f "$TERMINAL_PATH" ]]; then
        return 1
    fi

    set_status starting_terminal

    log "Starting MetaTrader 5"
    log "$TERMINAL_PATH"

    "$WINE_BIN" "$TERMINAL_PATH" \
        >/tmp/mt5.log 2>&1 &

    MT5_PID=$!

    sleep 5

    if mt5_running; then

        set_status terminal_started

        log "MetaTrader 5 running"

        return 0

    fi

    log "MetaTrader 5 failed to start"

    tail -n 100 /tmp/mt5.log || true

    return 1
}


if [[ -f "$TERMINAL_PATH" ]]; then

    start_mt5 || true

else

    log "Waiting for interactive MT5 installation"

fi


# =========================================================
# Supervisor loop
# =========================================================

MT5_FAILURES=0

while true; do

    # -----------------------------------------------------
    # Core infrastructure
    # -----------------------------------------------------

    if ! process_running "$XVFB_PID"; then
        fatal xvfb_stopped
    fi

    if ! process_running "$VNC_PID"; then
        fatal vnc_stopped
    fi

    if ! process_running "$NOVNC_PID"; then
        fatal novnc_stopped
    fi

    if ! process_running "$NGINX_PID"; then
        fatal nginx_stopped
    fi

    if ! process_running "$BRIDGE_PID"; then
        fatal bridge_stopped
    fi


    # -----------------------------------------------------
    # Detect MT5 installed during interactive bootstrap
    # -----------------------------------------------------

    if [[ ! -f "$TERMINAL_PATH" ]]; then

        FOUND_TERMINAL="$(
            find "$WINEPREFIX/drive_c" \
                -type f \
                -iname 'terminal64.exe' \
                -print \
                -quit 2>/dev/null || true
        )"

        if [[ -n "$FOUND_TERMINAL" ]]; then

            TERMINAL_PATH="$FOUND_TERMINAL"

            export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"

            log "Detected completed MT5 installation"

            start_mt5 || true

        fi

    # -----------------------------------------------------
    # MT5 crash recovery
    # -----------------------------------------------------

    elif ! mt5_running; then

        MT5_FAILURES=$((MT5_FAILURES + 1))

        set_status terminal_restarting

        log "MT5 is not running."
        log "Restart attempt: $MT5_FAILURES"

        case "$MT5_FAILURES" in
            1)
                BACKOFF=5
                ;;
            2)
                BACKOFF=10
                ;;
            3)
                BACKOFF=30
                ;;
            *)
                BACKOFF=60
                ;;
        esac

        sleep "$BACKOFF"

        if start_mt5; then

            MT5_FAILURES=0

        elif (( MT5_FAILURES >= 5 )); then

            log "MT5 repeatedly failed to start."

            fatal terminal_unhealthy

        fi

    else

        MT5_FAILURES=0

    fi

    sleep 5

done