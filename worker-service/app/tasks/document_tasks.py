from __future__ import annotations

import uuid
from typing import Any

from celery import Task
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.config import get_settings
from app.services.db_service import update_document_status

logger = get_task_logger(__name__)
settings = get_settings()


class BaseTaskWithRetry(Task):
    """
    Base task class with automatic retry on failure.
    All our tasks inherit from this so retry logic is centralised.
    """
    abstract = True
    max_retries = 3
    default_retry_delay = 60  # seconds

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:
        logger.warning(
            "task_retrying",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
        )
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs) -> None:
        logger.info(
            "task_succeeded",
            task_id=task_id,
            task_name=self.name,
        )
        super().on_success(retval, task_id, args, kwargs)


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.document_tasks.process_document",
)
def process_document(self, document_id: str, user_id: str) -> dict[str, Any]:
    """
    Background task: process a document after upload.

    Why Celery for this?
    - Document processing (chunking + embedding) can take 10-30 seconds
    - We don't want the HTTP request to hang that long
    - If it fails, Celery retries automatically
    - Multiple documents can be processed in parallel across workers

    Flow:
    1. Mark document as 'processing'
    2. Call document-service API to trigger embedding
    3. Mark document as 'ready' or 'failed'
    """
    logger.info(
        "process_document_started",
        document_id=document_id,
        user_id=user_id,
    )

    try:
        # Update status to processing
        update_document_status(document_id, "processing")

        # In a real system, we'd call document-service here via HTTP
        # For now we demonstrate the task structure
        # import httpx
        # httpx.post(f"{settings.document_service_url}/api/v1/documents/{document_id}/embed")

        update_document_status(document_id, "ready")

        logger.info("process_document_complete", document_id=document_id)
        return {"document_id": document_id, "status": "ready"}

    except Exception as exc:
        logger.error(
            "process_document_failed",
            document_id=document_id,
            error=str(exc),
        )
        update_document_status(document_id, "failed")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.document_tasks.delete_document_chunks",
)
def delete_document_chunks(self, document_id: str) -> dict[str, Any]:
    """
    Background task: clean up chunks after document deletion.
    Runs async so the delete HTTP response is instant.
    """
    logger.info("delete_chunks_started", document_id=document_id)
    try:
        # DB cleanup would happen here
        logger.info("delete_chunks_complete", document_id=document_id)
        return {"document_id": document_id, "chunks_deleted": True}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
