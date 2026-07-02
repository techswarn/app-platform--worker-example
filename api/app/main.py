import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.celery_client import celery_client

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

    if result.state == "PROGRESS":
        response["meta"] = result.info
    elif result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info)

    return response
