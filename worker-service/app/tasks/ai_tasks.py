from __future__ import annotations

from typing import Any

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.config import get_settings
from app.tasks.document_tasks import BaseTaskWithRetry

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.ai_tasks.generate_document_summary",
)
def generate_document_summary(
    self,
    document_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    Background task: generate an AI summary for a document.

    Why background? Summarizing a long document can take 30+ seconds.
    We trigger this after document processing completes and store
    the result — user polls for completion or gets notified.
    """
    logger.info(
        "generate_summary_started",
        document_id=document_id,
        user_id=user_id,
    )

    try:
        # In production: fetch document content from DB,
        # call ai-service /api/v1/inference/templates/render with
        # template_name='summarize', then store the result.
        #
        # import httpx
        # response = httpx.post(
        #     f"{settings.ai_service_url}/api/v1/inference/templates/render",
        #     json={
        #         "template_name": "summarize",
        #         "variables": {"text": document_content}
        #     },
        #     headers={"Authorization": f"Bearer {internal_token}"},
        # )

        logger.info("generate_summary_complete", document_id=document_id)
        return {
            "document_id": document_id,
            "summary": "Summary generated successfully",
        }

    except Exception as exc:
        logger.error(
            "generate_summary_failed",
            document_id=document_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)


@celery_app.task(
    name="app.tasks.ai_tasks.cleanup_old_results",
)
def cleanup_old_results() -> dict[str, Any]:
    """
    Periodic task: remove stale Celery results from Redis.
    Scheduled every hour via beat_schedule in celery_app.py.
    """
    logger.info("cleanup_started")
    # celery_app.backend.cleanup() would run here in production
    logger.info("cleanup_complete")
    return {"status": "cleaned"}


@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    name="app.tasks.ai_tasks.batch_embed_documents",
)
def batch_embed_documents(
    self,
    document_ids: list[str],
    user_id: str,
) -> dict[str, Any]:
    """
    Background task: re-embed multiple documents in batch.
    Useful when switching embedding models — re-process everything.
    Uses Celery chord/group for parallel processing in production.
    """
    logger.info(
        "batch_embed_started",
        num_documents=len(document_ids),
        user_id=user_id,
    )

    results = []
    for doc_id in document_ids:
        try:
            # Each document processed individually
            # In production: use celery group() for true parallelism
            results.append({"document_id": doc_id, "status": "queued"})
        except Exception as exc:
            results.append({"document_id": doc_id, "status": "failed", "error": str(exc)})

    logger.info(
        "batch_embed_complete",
        num_documents=len(document_ids),
        num_queued=len(results),
    )
    return {"results": results}
