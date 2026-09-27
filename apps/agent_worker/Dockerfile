# syntax=docker/dockerfile:1
FROM python:3.13-slim
WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Source-only edits must not invalidate the large research dependency download.
COPY pyproject.toml ./
COPY infra/docker/install_dependencies.py /tmp/install_dependencies.py
RUN --mount=type=cache,id=matrades-pip,target=/root/.cache/pip,sharing=locked \
    python /tmp/install_dependencies.py

RUN --mount=type=cache,id=matrades-pip,target=/root/.cache/pip,sharing=locked \
    pip install psycopg2-binary

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && curl -fsSL https://chatgpt.com/codex/install.sh | sh \
    && test -x /root/.local/bin/codex \
    && apt-get purge --yes --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"
RUN codex --version

COPY . .
RUN pip install --no-deps --no-build-isolation .
RUN chmod 755 /app/apps/agent_worker/entrypoint.sh
CMD ["/app/apps/agent_worker/entrypoint.sh"]
