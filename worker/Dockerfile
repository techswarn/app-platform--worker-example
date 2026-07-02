FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Pool/concurrency come from CELERY_POOL / CELERY_CONCURRENCY (see
# app/celery_app.py) so they're configurable via env vars without editing
# this file or the CLI command.
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
