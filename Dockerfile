FROM python:3.13-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------
# WineHQ + desktop/runtime dependencies
# ---------------------------------------------------------

RUN dpkg --add-architecture i386 \
    && mkdir -pm755 /etc/apt/keyrings \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        gnupg \
        procps \
        psmisc \
        xvfb \
        xauth \
        x11-utils \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        nginx \
        apache2-utils \
        winbind \
        cabextract \
        fonts-liberation \
        fonts-dejavu-core \
    && wget -O /etc/apt/keyrings/winehq-archive.key \
        https://dl.winehq.org/wine-builds/winehq.key \
    && wget -NP /etc/apt/sources.list.d/ \
        https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
    && apt-get update \
    && apt-get install -y --install-recommends \
        winehq-stable \
    && rm -rf /var/lib/apt/lists/*

# Verify Wine exists, but DON'T initialize a prefix at build time.
RUN wine --version

# ---------------------------------------------------------
# Application
# ---------------------------------------------------------

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir . \
    && chmod +x /app/start.sh

# ---------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------

ENV DISPLAY=:99 \
    WINEARCH=win64 \
    WINEPREFIX=/data/wineprefix \
    WINEDEBUG=-all \
    PYTHONUNBUFFERED=1

# Railway volume should be mounted at /data.
VOLUME ["/data"]

ENTRYPOINT ["/app/start.sh"]