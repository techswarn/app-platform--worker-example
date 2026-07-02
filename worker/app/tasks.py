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
def run_long_task(self, label: str = "task", step: int = 1, total: int = TOTAL_STEPS):
    # Deploy-safety: instead of one 660s task, this runs one STEP_SECONDS
    # (~10s) chunk of work, then hands off to a *new* broker message for the
    # next step via self.replace(). If App Platform SIGKILLs this container
    # mid-step (e.g. during a deploy, once the grace period elapses), only
    # the current ~10s step is lost -- task_acks_late + a short
    # broker visibility_timeout (see celery_app.py) mean that unacked step
    # gets redelivered and retried within seconds, and every step already
    # completed stays done because it ran (and acked) as its own message.
    # The alternative -- one long-running task -- would lose the *entire*
    # ~11 minutes of progress on every kill.
    time.sleep(STEP_SECONDS)

    percent = round(step / total * 100, 1)

    if step < total:
        self.update_state(
            state="PROGRESS",
            meta={"current": step, "total": total, "percent": percent, "label": label},
        )
        # Same task_id, new message: keeps /api/tasks/{task_id} polling
        # working unchanged while making each unit of work independently
        # durable.
        raise self.replace(run_long_task.si(label, step + 1, total))

    return {
        "label": label,
        "current": total,
        "total": total,
        "percent": 100.0,
        "duration_seconds": total * STEP_SECONDS,
    }
