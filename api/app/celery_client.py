import os
import ssl

from celery import Celery

# The API only enqueues tasks and polls results -- it never imports the
# worker's task code, so this Celery instance has no `include`. Tasks are
# submitted by name via send_task() (see TASK_NAME in main.py).
BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
)
RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
)

celery_client = Celery("api", broker=BROKER_URL, backend=RESULT_BACKEND)

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
    celery_client.conf.broker_use_ssl = {"ssl_cert_reqs": _CERT_REQS}
if RESULT_BACKEND.startswith("rediss://"):
    celery_client.conf.redis_backend_use_ssl = {"ssl_cert_reqs": _CERT_REQS}
