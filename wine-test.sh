#!/usr/bin/env bash

set -u

export DISPLAY=:99
export WINEPREFIX=/tmp/wine-test
export WINEDEBUG=err+all

unset WINEARCH

export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe

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
    echo "Xvfb failed"
    cat /tmp/xvfb.log
    exit 1
fi

echo "Xvfb OK"

echo
echo "======================================"
echo "Wine environment"
echo "======================================"

wine --version

echo "Kernel:"
uname -a

echo "Architecture:"
dpkg --print-architecture
dpkg --print-foreign-architectures

echo
echo "Vulkan libraries:"

ldconfig -p | grep -i vulkan || true

echo
echo "Wine processes before test:"

ps aux | grep -E 'wine|wineserver' || true


echo
echo "======================================"
echo "Creating clean Wine prefix"
echo "======================================"

wineserver -k 2>/dev/null || true
wineserver -w 2>/dev/null || true

rm -rf "$WINEPREFIX"

mkdir -p "$WINEPREFIX"

echo
echo "Starting wineserver"

wineserver -p

sleep 2

echo
echo "Wineserver process:"

ps aux | grep wineserver || true


echo
echo "======================================"
echo "Running wineboot"
echo "======================================"

wineboot --init

RESULT=$?

echo
echo "wineboot exit code: $RESULT"


echo
echo "======================================"
echo "Wine processes after wineboot"
echo "======================================"

ps aux | grep -E 'wine|services|rpcss' || true


echo
echo "======================================"
echo "Prefix contents"
echo "======================================"

find "$WINEPREFIX" \
    -maxdepth 2 \
    -type f \
    -print \
    2>/dev/null | head -100


if [[ "$RESULT" -eq 0 ]]; then

    echo
    echo "======================================"
    echo "Testing cmd.exe"
    echo "======================================"

    wine cmd /c echo WINE_RUNTIME_OK

fi


echo
echo "======================================"
echo "Diagnostic finished"
echo "Container remains alive"
echo "======================================"

while true; do
    sleep 3600
done