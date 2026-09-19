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
        fonts-dejavu-core \
        libvulkan1 \
        libvulkan1:i386 \
        mesa-vulkan-drivers \
        mesa-vulkan-drivers:i386 \
        libgl1 \
        libgl1:i386 \
        libglx-mesa0 \
        libglx-mesa0:i386 \
        libx11-6 \
        libx11-6:i386 \
        libxext6 \
        libxext6:i386 \
        libxrender1 \
        libxrender1:i386 \
        libfreetype6 \
        libfreetype6:i386 && \
    rm -rf /var/lib/apt/lists/*

ENV LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe 
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


# # ---------------------------------------------------------
# # Verify Wine installation during BUILD
# # ---------------------------------------------------------

RUN set -eux; \
    wine --version; \
    which wine; \
    which wineboot; \
    dpkg --print-architecture; \
    dpkg --print-foreign-architectures; \
    dpkg -l | grep -E 'wine|libwine'


# ---------------------------------------------------------
# Python application
# ---------------------------------------------------------

WORKDIR /app

COPY . /app


# ---------------------------------------------------------
# Python virtual environment
# ---------------------------------------------------------

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir .


ENV PATH="/opt/venv/bin:${PATH}"


# ---------------------------------------------------------
# Runtime
# ---------------------------------------------------------

ENV WINEPREFIX=/tmp/wineprefix \
    WINEDEBUG=-all \
    PYTHONUNBUFFERED=1


RUN chmod +x /app/wine-test.sh


ENTRYPOINT ["/app/wine-test.sh"]