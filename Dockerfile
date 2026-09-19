FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------
# Enable 32-bit architecture
# ---------------------------------------------------------

RUN dpkg --add-architecture i386

# ---------------------------------------------------------
# Base dependencies
# ---------------------------------------------------------

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        wget \
        curl \
        gnupg \
        software-properties-common \
        procps \
        psmisc \
        python3 \
        python3-pip \
        python3-venv \
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
        fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*


# ---------------------------------------------------------
# WineHQ repository
# ---------------------------------------------------------

RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key \
        https://dl.winehq.org/wine-builds/winehq.key && \
    wget -NP /etc/apt/sources.list.d/ \
        https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources


# ---------------------------------------------------------
# Install Wine
#
# IMPORTANT:
# --install-recommends ensures the required Wine runtime
# components and 32-bit libraries are installed.
# ---------------------------------------------------------

RUN apt-get update && \
    apt-get install -y --install-recommends \
        winehq-stable && \
    rm -rf /var/lib/apt/lists/*


RUN set -eux; \

    mkdir -p /tmp/.X11-unix; \

    chmod 1777 /tmp/.X11-unix; \

    Xvfb :98 -screen 0 1024x768x24 -ac -nolisten tcp >/tmp/xvfb-test.log 2>&1 & \

    XVFB_PID=$!; \

    sleep 2; \

    export DISPLAY=:98; \

    export WINEARCH=win64; \

    export WINEPREFIX=/tmp/wine-test; \

    export WINEDEBUG=err+all; \

    wine --version; \

    wineboot --init; \

    wine cmd /c echo WINE_TEST_OK; \

    wineserver -k || true; \

    kill "$XVFB_PID" || true; \

    rm -rf /tmp/wine-test

# # ---------------------------------------------------------
# # Verify Wine installation during BUILD
# # ---------------------------------------------------------

# RUN set -eux; \
#     wine --version; \
#     which wine; \
#     which wineboot; \
#     dpkg --print-architecture; \
#     dpkg --print-foreign-architectures; \
#     dpkg -l | grep -E 'wine|libwine'


# # ---------------------------------------------------------
# # Python application
# # ---------------------------------------------------------

# WORKDIR /app

# COPY . /app


# # ---------------------------------------------------------
# # Python virtual environment
# # ---------------------------------------------------------

# RUN python3 -m venv /opt/venv && \
#     /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
#     /opt/venv/bin/pip install --no-cache-dir .


# ENV PATH="/opt/venv/bin:${PATH}"


# # ---------------------------------------------------------
# # Runtime
# # ---------------------------------------------------------

# ENV WINEARCH=win64 \
#     WINEPREFIX=/data/wineprefix-v3 \
#     WINEDEBUG=-all \
#     PYTHONUNBUFFERED=1


# RUN chmod +x /app/start.sh


# ENTRYPOINT ["/app/start.sh"]