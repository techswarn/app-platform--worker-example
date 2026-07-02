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

# The demo task is I/O-bound (time.sleep), not CPU-bound, so the "threads"
# pool (stdlib concurrent.futures, no extra deps) lets many tasks run at
# once per worker process without needing one CPU core per task -- unlike
# the default "prefork" pool, which is capped by CPU count and would run
# tasks one-at-a-time on a single-vCPU instance. Switch back to "prefork"
# if your real task becomes CPU-bound.
CELERY_POOL = os.environ.get("CELERY_POOL", "threads")
CELERY_CONCURRENCY = int(os.environ.get("CELERY_CONCURRENCY", "8"))

# How long the broker waits for an ack before assuming the worker that took
# a message died and redelivering it to someone else. Deliberately short
# (default 60s) because tasks.py breaks work into ~10s steps -- if a step
# never acks (container SIGKILLed mid-step during a deploy), we want it
# redelivered within seconds, not Redis/Kombu's 3600s default. Keep this
# comfortably above STEP_SECONDS so a step that's merely slow (not dead)
# isn't redelivered and double-executed.
CELERY_VISIBILITY_TIMEOUT = int(os.environ.get("CELERY_VISIBILITY_TIMEOUT", "60"))

celery_app.conf.update(
    task_track_started=True,
    result_expires=3600,
    # Long-running task: make sure the broker connection is retried on
    # startup and that a worker restart doesn't silently drop the job.
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    # If the worker process is killed while a task is running (SIGKILL, OOM,
    # deploy), put the message back on the queue instead of losing it.
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": CELERY_VISIBILITY_TIMEOUT},
    # Concurrent execution: up to CELERY_CONCURRENCY tasks run at the same
    # time per worker process. Override with env vars, or with the
    # `--pool`/`--concurrency` CLI flags (those take precedence over conf).
    worker_pool=CELERY_POOL,
    worker_concurrency=CELERY_CONCURRENCY,
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
