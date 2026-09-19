#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Matrades MT5 Runtime
# Railway + Wine + Xvfb + noVNC + FastAPI + nginx
# ============================================================


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

export WINEPREFIX="${MATRADES_MT5_WINE_PREFIX:-${WINEPREFIX:-/data/wineprefix}}"
export WINEDEBUG="${WINEDEBUG:--all}"

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

XVFB_PID=""
FLUXBOX_PID=""
VNC_PID=""
NOVNC_PID=""
BRIDGE_PID=""
NGINX_PID=""
MT5_PID=""


# ============================================================
# Helpers
# ============================================================

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}


set_status() {
    mkdir -p "$(dirname "$STATUS_PATH")"
    printf '%s\n' "$1" > "$STATUS_PATH"
    log "STATUS: $1"
}


process_running() {
    local pid="${1:-}"

    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}


mt5_running() {

    if process_running "${MT5_PID:-}"; then
        return 0
    fi

    pgrep -f 'terminal64\.exe' >/dev/null 2>&1
}


fatal() {

    local status="$1"

    set_status "$status"

    log "FATAL: $status"

    exit 1
}


# ============================================================
# Graceful shutdown
# ============================================================

shutdown_runtime() {

    log "Shutting down Matrades MT5 runtime"

    set_status shutting_down

    if mt5_running; then
        log "Stopping MT5"
        pkill -f 'terminal64\.exe' 2>/dev/null || true
    fi

    for pid in \
        "${NGINX_PID:-}" \
        "${BRIDGE_PID:-}" \
        "${NOVNC_PID:-}" \
        "${VNC_PID:-}" \
        "${FLUXBOX_PID:-}" \
        "${XVFB_PID:-}"
    do
        if process_running "$pid"; then
            kill "$pid" 2>/dev/null || true
        fi
    done

    wineserver -k 2>/dev/null || true

    exit 0
}

trap shutdown_runtime SIGTERM SIGINT


# ============================================================
# Validate configuration
# ============================================================

set_status starting

log "Starting Matrades MT5 runtime"

log "Architecture:"
log "  kernel:  $(uname -m)"
log "  Debian:  $(dpkg --print-architecture)"
log "  foreign: $(dpkg --print-foreign-architectures || true)"

log "Wine:"
"$WINE_BIN" --version


if [[ ! "$PUBLIC_PORT" =~ ^[0-9]+$ ]] ||
   (( PUBLIC_PORT < 1 || PUBLIC_PORT > 65535 )); then

    fatal invalid_public_port

fi


if [[ -z "${MATRADES_MT5_DESKTOP_USER:-}" ]]; then
    fatal desktop_username_missing
fi


if [[ -z "${MATRADES_MT5_DESKTOP_PASSWORD:-}" ]]; then
    fatal desktop_password_missing
fi


# ============================================================
# Persistent Wine storage
# ============================================================

mkdir -p "$WINEPREFIX"

log "Wine prefix: $WINEPREFIX"


# ============================================================
# X11 cleanup
#
# Railway/container restarts can occasionally leave stale X
# lock/socket files. Only remove them if :99 is NOT actually
# serving a working X server.
# ============================================================

export DISPLAY="${DISPLAY:-:99}"

DISPLAY_NUMBER="${DISPLAY#:}"

X_LOCK="/tmp/.X${DISPLAY_NUMBER}-lock"
X_SOCKET="/tmp/.X11-unix/X${DISPLAY_NUMBER}"

set_status starting_display

log "Preparing X display $DISPLAY"


if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then

    log "Existing X server on $DISPLAY is healthy"

else

    log "No healthy X server found on $DISPLAY"

    if [[ -f "$X_LOCK" ]]; then
        log "Removing stale X lock: $X_LOCK"
        rm -f "$X_LOCK"
    fi

    if [[ -e "$X_SOCKET" ]]; then
        log "Removing stale X socket: $X_SOCKET"
        rm -f "$X_SOCKET"
    fi

    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix

    log "Starting Xvfb on $DISPLAY"

    Xvfb "$DISPLAY" \
        -screen 0 1440x900x24 \
        -ac \
        -nolisten tcp \
        +extension GLX \
        +render \
        -noreset \
        >/tmp/matrades-xvfb.log 2>&1 &

    XVFB_PID=$!

    DISPLAY_READY=false

    for attempt in $(seq 1 60); do

        if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then

            DISPLAY_READY=true
            break

        fi

        if ! process_running "$XVFB_PID"; then

            log "Xvfb exited during startup"

            cat /tmp/matrades-xvfb.log || true

            fatal display_failed

        fi

        sleep 0.25

    done


    if [[ "$DISPLAY_READY" != "true" ]]; then

        log "X display failed to become ready"

        cat /tmp/matrades-xvfb.log || true

        fatal display_failed

    fi

fi

log "X display $DISPLAY is ready"


# ============================================================
# Fluxbox
# ============================================================

log "Starting Fluxbox"

fluxbox \
    >/tmp/matrades-fluxbox.log 2>&1 &

FLUXBOX_PID=$!


# ============================================================
# VNC
# ============================================================

log "Starting x11vnc"

x11vnc \
    -display "$DISPLAY" \
    -rfbport "$VNC_PORT" \
    -localhost \
    -forever \
    -shared \
    -nopw \
    -quiet \
    >/tmp/matrades-x11vnc.log 2>&1 &

VNC_PID=$!


# ============================================================
# WebSocket proxy for noVNC
#
# nginx serves /usr/share/novnc.
# websockify only handles the VNC WebSocket.
# ============================================================

log "Starting websockify"

websockify \
    "127.0.0.1:${NOVNC_PORT}" \
    "127.0.0.1:${VNC_PORT}" \
    >/tmp/matrades-websockify.log 2>&1 &

NOVNC_PID=$!


sleep 1


if ! process_running "$VNC_PID"; then

    cat /tmp/matrades-x11vnc.log || true
    fatal vnc_failed

fi


if ! process_running "$NOVNC_PID"; then

    cat /tmp/matrades-websockify.log || true
    fatal websockify_failed

fi


log "Remote desktop infrastructure ready"


# ============================================================
# Wine initialization
# ============================================================

set_status initializing_wine

log "Initializing Wine"


if ! timeout 180s \
    "$WINEBOOT_BIN" --init \
    >/tmp/matrades-wineboot.log 2>&1
then

    log "wineboot failed"

    cat /tmp/matrades-wineboot.log || true

    fatal wineboot_failed

fi


log "Testing Wine command execution"


if ! timeout 30s \
    "$WINE_BIN" cmd /c echo WINE_OK \
    >/tmp/matrades-winetest.log 2>&1
then

    log "Wine command test failed"

    cat /tmp/matrades-winetest.log || true

    fatal wine_test_failed

fi


log "Wine initialized successfully"


# ============================================================
# Desktop authentication
# ============================================================

umask 077

printf '%s\n' "$MATRADES_MT5_DESKTOP_PASSWORD" |
    htpasswd \
        -i \
        -c \
        -B \
        /tmp/matrades-mt5-desktop.htpasswd \
        "$MATRADES_MT5_DESKTOP_USER" \
        >/dev/null


# ============================================================
# Start Matrades MT5 bridge
# ============================================================

log "Starting Matrades MT5 bridge on port $BRIDGE_PORT"

uvicorn bridges.mt5.app:app \
    --host 127.0.0.1 \
    --port "$BRIDGE_PORT" \
    >/tmp/matrades-bridge.log 2>&1 &

BRIDGE_PID=$!


# ============================================================
# nginx
# ============================================================

sed \
    "s/__PORT__/$PUBLIC_PORT/g" \
    /app/bridges/mt5/nginx.conf.template \
    >/tmp/matrades-mt5-nginx.conf


if ! nginx -t -c /tmp/matrades-mt5-nginx.conf; then
    fatal nginx_configuration_failed
fi


log "Starting nginx on Railway port $PUBLIC_PORT"

nginx \
    -c /tmp/matrades-mt5-nginx.conf \
    -g 'daemon off;' \
    >/tmp/matrades-nginx.log 2>&1 &

NGINX_PID=$!


sleep 2


if ! process_running "$BRIDGE_PID"; then

    cat /tmp/matrades-bridge.log || true

    fatal bridge_failed

fi


if ! process_running "$NGINX_PID"; then

    cat /tmp/matrades-nginx.log || true

    fatal nginx_failed

fi


log "HTTP gateway ready on port $PUBLIC_PORT"


# ============================================================
# Locate MT5
# ============================================================

find_mt5() {

    if [[ -f "$TERMINAL_PATH" ]]; then
        return 0
    fi

    local found=""

    found="$(
        find "$WINEPREFIX/drive_c" \
            -type f \
            -iname 'terminal64.exe' \
            -print \
            -quit \
            2>/dev/null || true
    )"

    if [[ -n "$found" ]]; then

        TERMINAL_PATH="$found"

        export MATRADES_MT5_TERMINAL_PATH="$TERMINAL_PATH"

        log "Found MT5 at: $TERMINAL_PATH"

        return 0

    fi

    return 1
}


# ============================================================
# Start MT5
# ============================================================

start_mt5() {

    if ! find_mt5; then
        return 1
    fi

    set_status starting_terminal

    log "Starting MetaTrader 5"
    log "Terminal: $TERMINAL_PATH"

    "$WINE_BIN" "$TERMINAL_PATH" \
        >/tmp/matrades-mt5.log 2>&1 &

    MT5_PID=$!

    sleep 5


    if mt5_running; then

        log "MetaTrader 5 is running"

        set_status terminal_started

        return 0

    fi


    log "MetaTrader 5 failed to start"

    tail -n 100 /tmp/matrades-mt5.log || true

    return 1
}


# ============================================================
# First-time MT5 bootstrap
# ============================================================

if find_mt5; then

    log "Existing MetaTrader 5 installation detected"

    start_mt5 || true

else

    set_status mt5_install_required

    log "MetaTrader 5 is not installed yet."


    if [[ -f "$INSTALLER_PATH" ]]; then

        log "Launching MT5 installer:"
        log "$INSTALLER_PATH"

        "$WINE_BIN" "$INSTALLER_PATH" \
            >/tmp/matrades-mt5-installer.log 2>&1 &

        log "Open the browser desktop to complete installation."

    else

        log "MT5 installer not found at:"
        log "$INSTALLER_PATH"

        log "Add mt5setup.exe or provide MT5_INSTALLER_PATH."

    fi

fi


# ============================================================
# Runtime supervisor
# ============================================================

MT5_FAILURES=0

log "Matrades MT5 runtime supervisor started"


while true; do

    # --------------------------------------------------------
    # X display
    # --------------------------------------------------------

    if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then

        fatal display_stopped

    fi


    # --------------------------------------------------------
    # VNC
    # --------------------------------------------------------

    if ! process_running "$VNC_PID"; then

        cat /tmp/matrades-x11vnc.log || true

        fatal vnc_stopped

    fi


    # --------------------------------------------------------
    # websockify
    # --------------------------------------------------------

    if ! process_running "$NOVNC_PID"; then

        cat /tmp/matrades-websockify.log || true

        fatal websockify_stopped

    fi


    # --------------------------------------------------------
    # Bridge
    # --------------------------------------------------------

    if ! process_running "$BRIDGE_PID"; then

        cat /tmp/matrades-bridge.log || true

        fatal bridge_stopped

    fi


    # --------------------------------------------------------
    # nginx
    # --------------------------------------------------------

    if ! process_running "$NGINX_PID"; then

        cat /tmp/matrades-nginx.log || true

        fatal nginx_stopped

    fi


    # --------------------------------------------------------
    # Detect completion of interactive MT5 installation
    # --------------------------------------------------------

    if ! find_mt5; then

        set_status mt5_install_required

        sleep 5
        continue

    fi


    # --------------------------------------------------------
    # MT5 crash recovery
    # --------------------------------------------------------

    if ! mt5_running; then

        MT5_FAILURES=$((MT5_FAILURES + 1))

        set_status terminal_restarting

        log "MT5 is not running"
        log "Restart attempt: $MT5_FAILURES"


        case "$MT5_FAILURES" in

            1)
                BACKOFF=5
                ;;

            2)
                BACKOFF=10
                ;;

            3)
                BACKOFF=20
                ;;

            4)
                BACKOFF=30
                ;;

            *)
                BACKOFF=60
                ;;

        esac


        log "Waiting ${BACKOFF}s before restart"

        sleep "$BACKOFF"


        if start_mt5; then

            MT5_FAILURES=0

        elif (( MT5_FAILURES >= 5 )); then

            log "MT5 failed repeatedly."

            # Exit so Railway can restart the entire runtime,
            # including Wine.
            fatal terminal_unhealthy

        fi

    else

        MT5_FAILURES=0

    fi


    sleep 5

done