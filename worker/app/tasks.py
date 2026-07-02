import time

from app.celery_app import celery_app

# Total runtime > 10 minutes, done as small steps so progress can be
# reported back to the UI while the task is running.
STEP_SECONDS = 10
TOTAL_STEPS = 66  # 66 * 10s = 660s = 11 minutes

# Keep this name in sync with TASK_NAME in api/app/main.py -- the API
# enqueues by name only, it does not import this module directly.
TASK_NAME = "app.tasks.run_long_task"


@celery_app.task(bind=True, name=TASK_NAME)
def run_long_task(self, label: str = "task"):
    for step in range(1, TOTAL_STEPS + 1):
        time.sleep(STEP_SECONDS)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": step,
                "total": TOTAL_STEPS,
                "percent": round(step / TOTAL_STEPS * 100, 1),
                "label": label,
            },
        )

    return {
        "label": label,
        "current": TOTAL_STEPS,
        "total": TOTAL_STEPS,
        "percent": 100.0,
        "duration_seconds": TOTAL_STEPS * STEP_SECONDS,
    }
