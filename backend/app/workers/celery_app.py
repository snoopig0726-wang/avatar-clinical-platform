from celery import Celery

from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "avatar_v1",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=86400,
    timezone="UTC",
    beat_schedule={
        "retention-every-hour": {
            "task": "retention.process_due_cases",
            "schedule": 3600.0,
        }
    },
    imports=("app.workers.retention", "app.workers.avatar_generation"),
)
