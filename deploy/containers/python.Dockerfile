FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 traderx
COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /uvx /usr/local/bin/
# Dependencies are resolved while the image is built, when network access is
# available. Runtime services live on a private network and must never attempt
# a dependency sync on startup.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY migrations ./migrations
COPY alembic.ini ./
RUN chown -R traderx:traderx /app
USER traderx
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH="/app/src:/app/apps/api:/app/apps/worker"
