import os
import ssl

from celery import Celery

# Valkey is wire-compatible with Redis, so the redis://(s) scheme and
# Celery's redis transport work unchanged against a Valkey server.
BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
)
RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
)

celery_app = Celery(
    "worker",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    result_expires=3600,
    # Long-running task: make sure the broker connection is retried on
    # startup and that a worker restart doesn't silently drop the job.
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Managed Valkey/Redis (e.g. DigitalOcean's DATABASE_URL) uses the rediss://
# scheme, which requires ssl_cert_reqs to be set explicitly or Celery raises
# "A rediss:// URL must have parameter ssl_cert_reqs...". Defaults to
# CERT_NONE (DO's managed Valkey uses a cert not in the system trust store);
# override via CELERY_SSL_CERT_REQS=required/optional/none if you supply a CA.
_CERT_REQS = {
    "required": ssl.CERT_REQUIRED,
    "optional": ssl.CERT_OPTIONAL,
    "none": ssl.CERT_NONE,
}[os.environ.get("CELERY_SSL_CERT_REQS", "none").lower()]

if BROKER_URL.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": _CERT_REQS}
if RESULT_BACKEND.startswith("rediss://"):
    celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": _CERT_REQS}
