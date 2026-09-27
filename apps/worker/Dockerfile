# syntax=docker/dockerfile:1
FROM python:3.13-slim
WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Source-only edits must not invalidate the large research dependency download.
COPY pyproject.toml ./
COPY infra/docker/install_dependencies.py /tmp/install_dependencies.py
RUN --mount=type=cache,id=matrades-pip,target=/root/.cache/pip,sharing=locked \
    python /tmp/install_dependencies.py

COPY . .
RUN pip install --no-deps --no-build-isolation .
CMD ["celery", "-A", "apps.worker.app.celery_app:celery_app", "worker", "--loglevel=INFO"]
