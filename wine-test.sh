#!/usr/bin/env bash

set -u

export DISPLAY=:99
export WINEPREFIX=/tmp/wine-test
export WINEDEBUG=err+all
export LIBGL_ALWAYS_SOFTWARE=1

unset WINEARCH

echo "======================================"
echo "Starting Xvfb"
echo "======================================"

rm -f /tmp/.X99-lock
rm -f /tmp/.X11-unix/X99

mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

Xvfb :99 \
    -screen 0 1024x768x24 \
    -ac \
    -nolisten tcp \
    >/tmp/xvfb.log 2>&1 &

sleep 2

if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "Xvfb FAILED"
    cat /tmp/xvfb.log
    exit 1
fi

echo "Xvfb OK"

echo
echo "======================================"
echo "Wine environment"
echo "======================================"

wine --version
uname -a

echo
echo "Wine binaries:"
command -v wine
command -v wineboot
command -v wineserver

echo
echo "======================================"
echo "Removing previous prefix"
echo "======================================"

wineserver -k 2>/dev/null || true
sleep 1

rm -rf "$WINEPREFIX"

echo "Prefix completely removed"

echo
echo "======================================"
echo "Creating prefix with wineboot"
echo "======================================"

wineboot --init
WINEBOOT_RESULT=$?

echo
echo "======================================"
echo "wineboot finished"
echo "======================================"

echo "wineboot exit code: $WINEBOOT_RESULT"

echo
echo "Prefix:"
ls -la "$WINEPREFIX" || true

echo
echo "Windows:"
ls -la "$WINEPREFIX/drive_c/windows" || true

echo
echo "System32:"
ls -la "$WINEPREFIX/drive_c/windows/system32" | head -30 || true

echo
echo "======================================"
echo "Wine processes"
echo "======================================"

ps aux | grep -E 'wine|services|rpcss' | grep -v grep || true

echo
echo "======================================"
echo "Testing cmd.exe"
echo "======================================"

wine cmd /c echo WINE_RUNTIME_OK
CMD_RESULT=$?

echo "cmd exit code: $CMD_RESULT"

echo
echo "======================================"
echo "Finished"
echo "wineboot=$WINEBOOT_RESULT"
echo "cmd=$CMD_RESULT"
echo "======================================"

while true; do
    sleep 3600
done