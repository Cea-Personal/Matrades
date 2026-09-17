FROM python:3.13-slim-bookworm

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Enable 32-bit architecture and install dependencies/Wine. The image also
# contains the Matrades bridge because Railway exposes one HTTP service port.
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        xvfb \
        procps \
        winbind \
        cabextract \
        libvulkan1 \
        libvulkan1:i386 && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key && \
    echo 'deb [signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/debian bookworm main' > /etc/apt/sources.list.d/winehq.list && \
    apt-get update && \
    apt-get install -y --install-recommends \
        winehq-stable \
        wine-stable-amd64 \
        wine-stable-i386:i386 && \
    rm -rf /var/lib/apt/lists/*

# Fail the image build early if Wine's loader is not actually available.
RUN wine --version && \
    test -n "$(find /usr/lib -type f -name kernel32.dll -print -quit)"

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir . && chmod +x /app/start.sh

ENV WINEPREFIX=/opt/wineprefix \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/start.sh"]
