FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------
# Base tools
# ---------------------------------------------------------

RUN apt-get update && \
    apt-get install -y \
        sudo \
        wget \
        curl \
        ca-certificates \
        gnupg \
        procps \
        psmisc \
        xvfb \
        xauth \
        x11-utils \
        fluxbox \
        x11vnc \
        novnc \
        websockify \
        libvulkan1 \
        mesa-vulkan-drivers \
        libgl1 \
        fonts-liberation \
        fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*


# ---------------------------------------------------------
# Create MT5 user
# ---------------------------------------------------------

RUN useradd \
        --create-home \
        --uid 1000 \
        --shell /bin/bash \
        mt5 && \
    echo "mt5 ALL=(ALL) NOPASSWD:ALL" \
        > /etc/sudoers.d/mt5 && \
    chmod 0440 /etc/sudoers.d/mt5


# ---------------------------------------------------------
# Application directory
# ---------------------------------------------------------

WORKDIR /app

COPY --chown=mt5:mt5 official-mt5-test.sh /app/official-mt5-test.sh

RUN chmod +x /app/official-mt5-test.sh && \
    mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix


# ---------------------------------------------------------
# Run installer as normal user
# ---------------------------------------------------------

USER mt5

ENV HOME=/home/mt5 \
    DISPLAY=:99 \
    WINEDEBUG=-all

ENTRYPOINT ["/app/official-mt5-test.sh"]