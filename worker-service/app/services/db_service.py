"""Illustrative worker extension; task results do not represent persisted work.

The document REST service performs the actual upload and embedding pipeline.
These examples do not call that pipeline or persist summaries/status changes.
"""
from __future__ import annotations

from shared.logging import get_logger

logger = get_logger(__name__)


def update_document_status(document_id: str, status: str) -> None:
    """
    Update document status in the database.

    In production this uses SQLAlchemy sync engine since Celery
    tasks are synchronous. For async Celery (with gevent/eventlet),
    you'd use asyncpg directly.

    We keep this as a thin service layer so tasks don't have
    DB logic scattered through them.
    """
    # Production implementation:
    # from sqlalchemy import create_engine, text
    # from app.config import get_settings
    # settings = get_settings()
    # engine = create_engine(settings.database_url)
    # with engine.connect() as conn:
    #     conn.execute(
    #         text("UPDATE documents SET status = :status WHERE id = :id"),
    #         {"status": status, "id": document_id}
    #     )
    #     conn.commit()

    logger.info(
        "document_status_updated",
        document_id=document_id,
        status=status,
    )
