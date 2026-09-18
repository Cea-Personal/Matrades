FROM python:3.13-slim
WORKDIR /app
COPY . .
COPY  ../infra/migration /app/migrations
RUN pip install --no-cache-dir .
CMD ["celery", "-A", "apps.worker.app.celery_app:celery_app", "worker", "--loglevel=INFO"]
