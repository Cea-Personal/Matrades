#!/usr/bin/env bash

set -u

export DISPLAY=:99
unset WINEARCH

echo "=== Starting Xvfb ==="

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

xdpyinfo -display :99 >/dev/null || {
    cat /tmp/xvfb.log
    exit 1
}

echo "=== Wine ==="

wine --version

echo "=== Architecture ==="

uname -m
dpkg --print-architecture
dpkg --print-foreign-architectures

test_prefix() {

    prefix="$1"

    echo
    echo "======================================"
    echo "Testing: $prefix"
    echo "======================================"

    rm -rf "$prefix"
    mkdir -p "$prefix"

    WINEPREFIX="$prefix" \
    WINEDEBUG=err+all \
        wineboot --init

    result=$?

    echo "wineboot exit code: $result"

    if [ "$result" -eq 0 ]; then

        WINEPREFIX="$prefix" \
            wine cmd /c echo WINE_OK

        WINEPREFIX="$prefix" \
            wineserver -k || true

    fi
}

test_prefix /tmp/wine-test-a

test_prefix /var/tmp/wine-test-b

test_prefix /data/wine-test-c

echo
echo "======================================"
echo "Wine diagnostics complete"
echo "Container will remain running"
echo "======================================"

while true; do
    sleep 3600
done