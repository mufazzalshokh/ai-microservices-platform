from __future__ import annotations

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from shared.logging import configure_logging, get_logger

from app.config import get_settings

settings = get_settings()

configure_logging(level=settings.log_level, service_name=settings.service_name)
logger = get_logger(__name__)

# ── Celery application ────────────────────────────────────────────────────────
celery_app = Celery(
    "worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.document_tasks",
        "app.tasks.ai_tasks",
    ],
)

# ── Celery configuration ──────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_acks_late=True,          # ack after task completes, not when received
    task_reject_on_worker_lost=True,  # requeue if worker dies mid-task
    worker_prefetch_multiplier=1,  # one task at a time per worker (fair dispatch)

    # Result expiry
    result_expires=3600,          # results live in Redis for 1 hour

    # Retry defaults
    task_max_retries=settings.task_max_retries,

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Beat schedule (periodic tasks)
    beat_schedule={
        "cleanup-expired-results": {
            "task": "app.tasks.ai_tasks.cleanup_old_results",
            "schedule": 3600.0,  # every hour
        },
    },
)


# ── Lifecycle signals ─────────────────────────────────────────────────────────
@worker_ready.connect
def on_worker_ready(**kwargs) -> None:
    logger.info("celery_worker_ready", service=settings.service_name)


@worker_shutdown.connect
def on_worker_shutdown(**kwargs) -> None:
    logger.info("celery_worker_shutdown", service=settings.service_name)
