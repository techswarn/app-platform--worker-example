import json
import os
import ssl

import redis

# Separate from celery_app.py's Celery client on purpose: this is a plain
# Valkey key we read/write directly, used as the durable progress record
# for a running task. Celery's own PROGRESS state (set via
# self.update_state()) isn't reliable here because it gets overwritten by
# the next step's STARTED transition the moment self.replace() hands off
# (see tasks.py) -- by the time a poller reads it, it's usually already
# clobbered.
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
_TTL_SECONDS = 3600  # matches Celery's result_expires


def set_progress(task_id: str, data: dict) -> None:
    _client.set(_KEY_PREFIX + task_id, json.dumps(data), ex=_TTL_SECONDS)


def get_progress(task_id: str) -> dict | None:
    raw = _client.get(_KEY_PREFIX + task_id)
    return json.loads(raw) if raw else None


def clear_progress(task_id: str) -> None:
    _client.delete(_KEY_PREFIX + task_id)
