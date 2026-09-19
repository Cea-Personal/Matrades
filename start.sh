#!/usr/bin/env bash

set -u


# ============================================================
# Configuration
# ============================================================

export DISPLAY=:99
export HOME=/home/mt5
export WINEPREFIX=/home/mt5/.wine

unset WINEARCH

export WINEDEBUG=err+all
export LIBGL_ALWAYS_SOFTWARE=1


echo
echo "======================================"
echo "Matrades Wine Diagnostic"
echo "======================================"

echo
echo "Date:"
date

echo
echo "User:"
id

echo
echo "HOME:"
echo "$HOME"

echo
echo "WINEPREFIX:"
echo "$WINEPREFIX"

echo
echo "DISPLAY:"
echo "$DISPLAY"

echo
echo "Wine version:"
wine --version

echo
echo "Kernel:"
uname -a

echo
echo "Architecture:"
dpkg --print-architecture
dpkg --print-foreign-architectures


# ============================================================
# Wine binaries
# ============================================================

echo
echo "======================================"
echo "Wine binaries"
echo "======================================"

command -v wine
command -v wineboot
command -v wineserver


# ============================================================
# Vulkan/OpenGL libraries
# ============================================================

echo
echo "======================================"
echo "Vulkan libraries"
echo "======================================"

ldconfig -p | grep libvulkan.so.1 || true


# ============================================================
# Start virtual X display
# ============================================================

echo
echo "======================================"
echo "Starting Xvfb"
echo "======================================"

rm -f /tmp/.X99-lock
rm -f /tmp/.X11-unix/X99

mkdir -p /tmp/.X11-unix

Xvfb :99 \
    -screen 0 1024x768x24 \
    -ac \
    -nolisten tcp \
    >/tmp/xvfb.log 2>&1 &

XVFB_PID=$!

echo "Xvfb PID: $XVFB_PID"

sleep 3


# ============================================================
# Verify X display
# ============================================================

if xdpyinfo -display :99 >/dev/null 2>&1; then

    echo "Xvfb OK"

else

    echo
    echo "======================================"
    echo "XVFB FAILED"
    echo "======================================"

    cat /tmp/xvfb.log || true

    while true; do
        sleep 3600
    done

fi


# ============================================================
# Clean previous Wine processes
# ============================================================

echo
echo "======================================"
echo "Stopping previous Wine server"
echo "======================================"

wineserver -k 2>/dev/null || true

sleep 2


# ============================================================
# Delete previous prefix
# ============================================================

echo
echo "======================================"
echo "Removing previous Wine prefix"
echo "======================================"

rm -rf "$WINEPREFIX"

if [[ -e "$WINEPREFIX" ]]; then

    echo "ERROR: Wine prefix still exists"

    ls -la "$WINEPREFIX" || true

else

    echo "Wine prefix removed successfully"

fi


# ============================================================
# Show disk/filesystem information
# ============================================================

echo
echo "======================================"
echo "Filesystem information"
echo "======================================"

df -h "$HOME" || true

mount | grep -E '/home|overlay|tmp' || true


# ============================================================
# Initialize Wine
# ============================================================

echo
echo "======================================"
echo "Creating Wine prefix"
echo "======================================"

echo "Running:"
echo "wineboot --init"

echo

timeout 120s wineboot --init

WINEBOOT_RESULT=$?


# ============================================================
# Wineboot result
# ============================================================

echo
echo "======================================"
echo "Wineboot finished"
echo "======================================"

echo "Exit code: $WINEBOOT_RESULT"

if [[ "$WINEBOOT_RESULT" -eq 124 ]]; then

    echo
    echo "WINEBOOT TIMED OUT"

elif [[ "$WINEBOOT_RESULT" -eq 0 ]]; then

    echo
    echo "WINEBOOT SUCCESS"

else

    echo
    echo "WINEBOOT FAILED"

fi


# ============================================================
# Inspect Wine prefix
# ============================================================

echo
echo "======================================"
echo "Wine prefix"
echo "======================================"

ls -la "$WINEPREFIX" 2>/dev/null || true


echo
echo "======================================"
echo "C drive"
echo "======================================"

ls -la "$WINEPREFIX/drive_c" \
    2>/dev/null || true


echo
echo "======================================"
echo "Windows directory"
echo "======================================"

ls -la "$WINEPREFIX/drive_c/windows" \
    2>/dev/null || true


echo
echo "======================================"
echo "System32"
echo "======================================"

ls -la "$WINEPREFIX/drive_c/windows/system32" \
    2>/dev/null | head -50 || true


# ============================================================
# Look specifically for kernel32
# ============================================================

echo
echo "======================================"
echo "kernel32.dll"
echo "======================================"

find "$WINEPREFIX" \
    -iname 'kernel32.dll' \
    -print \
    2>/dev/null || true


# ============================================================
# Wine processes
# ============================================================

echo
echo "======================================"
echo "Wine processes"
echo "======================================"

ps aux | \
    grep -E \
    'wine|wineserver|services.exe|rpcss.exe|explorer.exe|winedevice' | \
    grep -v grep || true


# ============================================================
# Test Windows command processor
# ============================================================

CMD_RESULT=999

if [[ "$WINEBOOT_RESULT" -eq 0 ]]; then

    echo
    echo "======================================"
    echo "Testing cmd.exe"
    echo "======================================"

    timeout 30s wine cmd /c echo WINE_RUNTIME_OK

    CMD_RESULT=$?

    echo
    echo "cmd.exe exit code: $CMD_RESULT"

else

    echo
    echo "Skipping cmd.exe because wineboot failed"

fi


# ============================================================
# Final result
# ============================================================

echo
echo "======================================"
echo "FINAL RESULT"
echo "======================================"

echo "wineboot=$WINEBOOT_RESULT"
echo "cmd=$CMD_RESULT"

if [[ "$WINEBOOT_RESULT" -eq 0 ]] && \
   [[ "$CMD_RESULT" -eq 0 ]]; then

    echo
    echo "**************************************"
    echo "WINE RUNTIME TEST PASSED"
    echo "**************************************"

else

    echo
    echo "**************************************"
    echo "WINE RUNTIME TEST FAILED"
    echo "**************************************"

fi


# ============================================================
# Keep Railway container alive
# ============================================================

echo
echo "Container will remain running for diagnostics."

while true; do
    sleep 3600
done