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
