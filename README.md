# api-worker

Two independent components sharing one Valkey broker:

- **api** — FastAPI app with an embedded UI. Submits jobs and polls status.
- **worker** — Celery worker that runs the actual (~11 minute) job.

The API never imports the worker's code; it enqueues by task name
(`app.tasks.run_long_task`) and reads results back through Celery's result
backend. Both point at the same Valkey instance via `CELERY_BROKER_URL` /
`CELERY_RESULT_BACKEND`.

## Layout

```
api/
  Dockerfile
  requirements.txt
  app/
    main.py            FastAPI routes + embedded UI
    celery_client.py   Celery client used only to send_task()/poll results
    templates/index.html

worker/
  Dockerfile
  requirements.txt
  app/
    celery_app.py      Celery app config
    tasks.py            run_long_task (~11 min, reports progress)

.do/app.yaml            DigitalOcean App Platform spec
```

## Run locally (no Docker)

You need a Valkey (or Redis) server reachable at `CELERY_BROKER_URL`. If you
don't already have one running locally, install it with your package manager
(e.g. `brew install valkey && valkey-server` or `apt install valkey-server`),
or point at a remote/managed instance instead.

In one terminal, start the worker:

```
cd worker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0
celery -A app.celery_app worker --loglevel=info
```

In another terminal, start the API:

```
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0
uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080, click "Start Task", watch progress update every
5 seconds until it completes (~11 minutes).

**Connecting to a managed Valkey (e.g. DigitalOcean's `DATABASE_URL`)**: it
uses the `rediss://` (TLS) scheme. Both `celery_app.py` and
`celery_client.py` detect this automatically and default to
`ssl_cert_reqs=CERT_NONE`. If you want strict certificate verification,
download the database's CA cert and set `CELERY_SSL_CERT_REQS=required`
(plus point Celery at the CA — see Celery's Redis SSL docs).

## Concurrent task execution

Multiple submitted tasks run in parallel, not one-at-a-time. The worker
uses Celery's `threads` pool (stdlib `concurrent.futures`, no extra
dependency) instead of the default `prefork` pool, because the demo task is
I/O-bound (`time.sleep`) rather than CPU-bound — `prefork` concurrency is
capped by CPU core count, which would serialize tasks on a single-vCPU
instance; `threads` doesn't have that limit.

Configured in `worker/app/celery_app.py` via env vars, with defaults baked
in so it works with no extra flags:

- `CELERY_POOL` (default `threads`) — set to `prefork` if you replace the
  demo task with real CPU-bound work.
- `CELERY_CONCURRENCY` (default `8`) — how many tasks one worker process
  runs at the same time.

To scale further, raise `CELERY_CONCURRENCY`, or add more worker instances
(`instance_count` in `.do/app.yaml`, or run a second `celery worker`
process locally) — each instance/process runs its own pool of
`CELERY_CONCURRENCY` concurrent tasks.

## Surviving deploys/restarts without losing an in-progress task

App Platform sends `SIGTERM`, waits `termination.grace_period_seconds`
(default 120s, max 600s), then `SIGKILL`s anything still running — on every
deploy, restart, or scaling event. A single ~11-minute task can't finish a
graceful shutdown in that window, so a naive implementation loses whatever
was in flight.

`worker/app/tasks.py` avoids this by never actually running for 11 minutes
in one go. `run_long_task` does one `STEP_SECONDS` (~10s) chunk, then calls
`self.replace(...)` to hand off to a *new* broker message for the next step,
under the same task id. That means:

- Each step is its own durable message. If the container is killed
  mid-step, only that ~10s of work is at risk — not the whole job.
- `task_acks_late=True` + `task_reject_on_worker_lost=True` +
  `broker_transport_options.visibility_timeout` (default 60s, env
  `CELERY_VISIBILITY_TIMEOUT`) mean an interrupted step's message goes back
  on the queue and gets picked up (by the new deployment's worker) within
  seconds, instead of Valkey/Redis's default 1-hour redelivery window.
- `/api/tasks/{task_id}` keeps working unchanged across the handoff, since
  `replace()` preserves the task id.
- `.do/app.yaml` sets `grace_period_seconds: 180` on the worker for extra
  margin — comfortable overkill since a single step only needs ~10s to
  finish, well under even the default 120s.

If you replace the demo task with real logic, keep it chunked the same way
(loop body → one step per `self.replace` call) rather than one long
function body, and make each step idempotent (safe to redo) since a step
can occasionally re-run after a redelivery.

## Deploy to DigitalOcean App Platform

`.do/app.yaml` defines:

- `api` (service) — builds from `api/Dockerfile` with build context `api/`, exposes port 8080.
- `celery-worker` (worker) — builds from `worker/Dockerfile` with build context `worker/`, no public port.
- `valkey` (database, `engine: VALKEY`) — managed broker/result backend, bound to both components via `${valkey.DATABASE_URL}`.

Each Dockerfile's own `CMD` is the run command — App Platform uses it as-is,
no `run_command` override needed.

Push this repo to GitHub, then add a `github:` block (repo/branch) under
each component in `.do/app.yaml` — commented placeholders are already there
— and deploy:

```
doctl apps create --spec .do/app.yaml
```

To update later:
```
doctl apps update <app-id> --spec .do/app.yaml
```
