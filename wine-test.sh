#!/usr/bin/env bash

set -u

export DISPLAY=:99
export WINEPREFIX=/tmp/wine-test
export WINEDEBUG=err+all

unset WINEARCH

export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe

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

XVFB_PID=$!

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

echo
echo "Kernel:"
uname -a

echo
echo "Architecture:"
dpkg --print-architecture
dpkg --print-foreign-architectures

echo
echo "Wine binaries:"
command -v wine
command -v wineboot
command -v wineserver

echo
echo "Vulkan:"
ldconfig -p | grep libvulkan.so.1 || true


echo
echo "======================================"
echo "Stopping old Wine processes"
echo "======================================"

wineserver -k 2>/dev/null || true
wineserver -w 2>/dev/null || true

pkill -f 'wineboot|winedevice|services.exe|rpcss.exe|explorer.exe' \
    2>/dev/null || true

sleep 1


echo
echo "======================================"
echo "Removing previous prefix"
echo "======================================"

rm -rf "$WINEPREFIX"

if [[ -e "$WINEPREFIX" ]]; then
    echo "ERROR: Prefix still exists"
    ls -la "$WINEPREFIX"
else
    echo "Prefix completely removed"
fi


echo
echo "======================================"
echo "Creating prefix with wineboot"
echo "======================================"

wineboot --init

RESULT=$?

echo
echo "wineboot exit code: $RESULT"


echo
echo "======================================"
echo "Prefix after wineboot"
echo "======================================"

ls -la "$WINEPREFIX" 2>/dev/null || true

echo
echo "Windows directory:"

ls -la "$WINEPREFIX/drive_c/windows" \
    2>/dev/null || echo "WINDOWS DIRECTORY MISSING"

echo
echo "System32 directory:"

ls -la "$WINEPREFIX/drive_c/windows/system32" \
    2>/dev/null | head -30 || echo "SYSTEM32 MISSING"


echo
echo "======================================"
echo "Wine processes"
echo "======================================"

ps aux | grep -E \
    'wine|wineserver|services.exe|rpcss.exe' \
    | grep -v grep || true


if [[ "$RESULT" -eq 0 ]]; then

    echo
    echo "======================================"
    echo "Testing cmd.exe"
    echo "======================================"

    wine cmd /c echo WINE_RUNTIME_OK

    CMD_RESULT=$?

    echo "cmd exit code: $CMD_RESULT"

else

    echo
    echo "wineboot FAILED"

fi


echo
echo "======================================"
echo "Diagnostic complete"
echo "======================================"

while true; do
    sleep 3600
done