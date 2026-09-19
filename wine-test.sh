#!/usr/bin/env bash

set -u

export HOME=/home/mt5
export WINEPREFIX=/home/mt5/.wine
export DISPLAY=:99
export WINEDEBUG=err+all
export LIBGL_ALWAYS_SOFTWARE=1

unset WINEARCH

echo "======================================"
echo "Matrades Wine Test"
echo "======================================"

echo "User:"
id

echo "HOME=$HOME"
echo "WINEPREFIX=$WINEPREFIX"

echo
echo "Home ownership:"
ls -ld "$HOME"

echo
echo "Wine:"
wine --version


# ------------------------------------------------------------
# Xvfb
# ------------------------------------------------------------

echo
echo "Starting Xvfb"

rm -f /tmp/.X99-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

Xvfb :99 \
    -screen 0 1024x768x24 \
    -ac \
    -nolisten tcp \
    >/tmp/xvfb.log 2>&1 &

sleep 3

if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "Xvfb FAILED"
    cat /tmp/xvfb.log

    while true; do
        sleep 3600
    done
fi

echo "Xvfb OK"


# ------------------------------------------------------------
# Clean prefix
# ------------------------------------------------------------

echo
echo "Removing previous prefix"

wineserver -k 2>/dev/null || true

rm -rf "$WINEPREFIX"

echo "Prefix removed"


# ------------------------------------------------------------
# Wineboot
# ------------------------------------------------------------

echo
echo "======================================"
echo "Creating Wine prefix"
echo "======================================"

timeout 120s wineboot --init

RESULT=$?

echo
echo "wineboot exit code: $RESULT"


# ------------------------------------------------------------
# Inspect result
# ------------------------------------------------------------

echo
echo "Prefix ownership:"

ls -ld "$WINEPREFIX" 2>/dev/null || true

echo
echo "Windows directory:"

ls -ld "$WINEPREFIX/drive_c/windows" 2>/dev/null || true

echo
echo "System32:"

ls -ld "$WINEPREFIX/drive_c/windows/system32" 2>/dev/null || true

echo
echo "kernel32.dll:"

find "$WINEPREFIX" \
    -iname kernel32.dll \
    -print \
    2>/dev/null || true


# ------------------------------------------------------------
# cmd test
# ------------------------------------------------------------

if [[ "$RESULT" -eq 0 ]]; then

    echo
    echo "======================================"
    echo "Testing Wine"
    echo "======================================"

    timeout 30s wine cmd /c echo WINE_RUNTIME_OK

    CMD_RESULT=$?

    echo "cmd result: $CMD_RESULT"

else

    CMD_RESULT=999

fi


echo
echo "======================================"
echo "RESULT"
echo "======================================"

echo "wineboot=$RESULT"
echo "cmd=$CMD_RESULT"

if [[ "$RESULT" -eq 0 ]] && [[ "$CMD_RESULT" -eq 0 ]]; then
    echo "WINE TEST PASSED"
else
    echo "WINE TEST FAILED"
fi


while true; do
    sleep 3600
done