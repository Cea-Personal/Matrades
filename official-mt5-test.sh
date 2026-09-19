#!/usr/bin/env bash

set -u

export HOME=/home/mt5
export DISPLAY=:99

echo "======================================"
echo "MetaTrader 5 Official Linux Test"
echo "======================================"

echo
echo "User:"
id

echo
echo "HOME:"
echo "$HOME"

echo
echo "OS:"
cat /etc/os-release


# ---------------------------------------------------------
# X display
# ---------------------------------------------------------

echo
echo "======================================"
echo "Starting Xvfb"
echo "======================================"

rm -f /tmp/.X99-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

Xvfb :99 \
    -screen 0 1440x900x24 \
    -ac \
    -nolisten tcp \
    >/tmp/xvfb.log 2>&1 &

XVFB_PID=$!

sleep 3

if ! xdpyinfo -display :99 >/dev/null 2>&1; then

    echo "Xvfb failed"

    cat /tmp/xvfb.log || true

    while true; do
        sleep 3600
    done
fi

echo "Xvfb OK"


# ---------------------------------------------------------
# Window manager
# ---------------------------------------------------------

fluxbox >/tmp/fluxbox.log 2>&1 &


# ---------------------------------------------------------
# Download official MetaQuotes Linux installer
# ---------------------------------------------------------

echo
echo "======================================"
echo "Downloading official MT5 Linux installer"
echo "======================================"

cd "$HOME"

wget \
    -O mt5linux.sh \
    https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/mt5linux.sh

chmod +x mt5linux.sh


echo
echo "Installer downloaded:"
ls -lh mt5linux.sh


# ---------------------------------------------------------
# Run official installer
# ---------------------------------------------------------

echo
echo "======================================"
echo "Starting official MetaQuotes installer"
echo "======================================"

./mt5linux.sh

INSTALL_RESULT=$?


echo
echo "======================================"
echo "Installer finished"
echo "======================================"

echo "exit=$INSTALL_RESULT"


# ---------------------------------------------------------
# Inspect installation
# ---------------------------------------------------------

echo
echo "MT5 directory:"

find "$HOME/.mt5" \
    -maxdepth 5 \
    -iname 'terminal64.exe' \
    -print \
    2>/dev/null || true


echo
echo "Wine version:"

wine --version 2>/dev/null || true


echo
echo "Installed prefix:"

ls -la "$HOME/.mt5" 2>/dev/null || true


echo
echo "======================================"
echo "Keeping container alive"
echo "======================================"

while true; do
    sleep 3600
done