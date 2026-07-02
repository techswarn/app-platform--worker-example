import json
import os
import ssl

import redis

# Mirrors worker/app/progress.py -- same Valkey instance, same key scheme.
# The API only ever reads this key; the worker is what writes/clears it.
BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", os.environ.get("VALKEY_URL", "redis://localhost:6379/0")
)

_CERT_REQS = {
    "required": ssl.CERT_REQUIRED,
    "optional": ssl.CERT_OPTIONAL,
    "none": ssl.CERT_NONE,
}[os.environ.get("CELERY_SSL_CERT_REQS", "none").lower()]

_client_kwargs = {"decode_responses": True}
if BROKER_URL.startswith("rediss://"):
    _client_kwargs["ssl_cert_reqs"] = _CERT_REQS

_client = redis.Redis.from_url(BROKER_URL, **_client_kwargs)

_KEY_PREFIX = "task-progress:"


def get_progress(task_id: str) -> dict | None:
    raw = _client.get(_KEY_PREFIX + task_id)
    return json.loads(raw) if raw else None
