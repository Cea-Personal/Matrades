FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
CMD ["celery", "-A", "apps.worker.app.celery_app:celery_app", "worker", "--loglevel=INFO"]
