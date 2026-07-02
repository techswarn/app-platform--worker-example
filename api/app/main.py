import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.celery_client import celery_client
from app.progress import get_progress

# Must match the `name=` given to the task in worker/app/tasks.py.
TASK_NAME = "app.tasks.run_long_task"

app = FastAPI(title="API")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class SubmitTaskRequest(BaseModel):
    label: str = "task"


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/tasks")
def submit_task(payload: SubmitTaskRequest):
    task_id = str(uuid.uuid4())
    celery_client.send_task(TASK_NAME, args=[payload.label], task_id=task_id)
    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    result = celery_client.AsyncResult(task_id)

    response = {"task_id": task_id, "state": result.state}

    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info)
    else:
        # Anything non-terminal (PENDING/STARTED/etc): prefer the explicit
        # progress record over Celery's own state. Because each step hands
        # off via self.replace(), Celery's built-in state flips to STARTED
        # again the instant the next step begins, clobbering the PROGRESS
        # state almost as soon as it's set -- the progress record in
        # Valkey (written just before each handoff) is what's actually
        # reliable to poll.
        progress = get_progress(task_id)
        if progress:
            response["state"] = "PROGRESS"
            response["meta"] = progress

    return response
