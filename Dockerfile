FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive


# ============================================================
# 1. Enable 32-bit packages for Wine
# ============================================================

RUN dpkg --add-architecture i386


# ============================================================
# 2. Base dependencies
# ============================================================

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        wget \
        curl \
        gnupg \
        procps \
        psmisc \
        xvfb \
        xauth \
        x11-utils \
        cabextract \
        winbind \
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


# ============================================================
# 3. Add official WineHQ repository
# ============================================================

RUN mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key \
        https://dl.winehq.org/wine-builds/winehq.key && \
    wget -NP /etc/apt/sources.list.d/ \
        https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources


# ============================================================
# 4. Install Wine
# ============================================================

RUN apt-get update && \
    apt-get install -y --install-recommends \
        winehq-stable && \
    rm -rf /var/lib/apt/lists/*


# ============================================================
# 5. Verify packages only
#
# IMPORTANT:
# Do NOT run wineboot during Docker build.
# ============================================================

RUN set -eux; \
    wine --version; \
    command -v wine; \
    command -v wineboot; \
    command -v wineserver; \
    dpkg --print-architecture; \
    dpkg --print-foreign-architectures; \
    dpkg -l | grep -E 'wine|libwine' || true


# ============================================================
# 6. Create dedicated non-root MT5/Wine user
# ============================================================

RUN useradd \
        --create-home \
        --uid 1000 \
        --shell /bin/bash \
        mt5 && \
    mkdir -p /app && \
    chown -R mt5:mt5 /home/mt5 /app


# ============================================================
# 7. Runtime environment
# ============================================================

ENV HOME=/home/mt5 \
    WINEPREFIX=/home/mt5/.wine \
    WINEDEBUG=err+all \
    LIBGL_ALWAYS_SOFTWARE=1


# ============================================================
# 8. Copy diagnostic script
# ============================================================

WORKDIR /app

COPY --chown=mt5:mt5 wine-test.sh /app/wine-test.sh

RUN chmod +x /app/wine-test.sh


# ============================================================
# 9. IMPORTANT: Wine runs as non-root
# ============================================================

USER mt5


# ============================================================
# 10. Diagnostic entrypoint
# ============================================================

ENTRYPOINT ["/app/wine-test.sh"]