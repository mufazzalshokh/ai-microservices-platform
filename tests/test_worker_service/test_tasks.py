from __future__ import annotations

import uuid


def test_process_document_task_exists(document_tasks):
    assert hasattr(document_tasks, "process_document")
    assert callable(document_tasks.process_document)


def test_delete_chunks_task_exists(document_tasks):
    assert hasattr(document_tasks, "delete_document_chunks")
    assert callable(document_tasks.delete_document_chunks)


def test_generate_summary_task_exists(ai_tasks):
    assert hasattr(ai_tasks, "generate_document_summary")
    assert callable(ai_tasks.generate_document_summary)


def test_cleanup_task_exists(ai_tasks):
    assert hasattr(ai_tasks, "cleanup_old_results")
    assert callable(ai_tasks.cleanup_old_results)


def test_batch_embed_task_exists(ai_tasks):
    assert hasattr(ai_tasks, "batch_embed_documents")
    assert callable(ai_tasks.batch_embed_documents)


def test_task_names_are_correct(document_tasks, ai_tasks):
    """Wrong task names = tasks silently never run in production."""
    assert document_tasks.process_document.name == \
        "app.tasks.document_tasks.process_document"
    assert document_tasks.delete_document_chunks.name == \
        "app.tasks.document_tasks.delete_document_chunks"
    assert ai_tasks.generate_document_summary.name == \
        "app.tasks.ai_tasks.generate_document_summary"
    assert ai_tasks.cleanup_old_results.name == \
        "app.tasks.ai_tasks.cleanup_old_results"
    assert ai_tasks.batch_embed_documents.name == \
        "app.tasks.ai_tasks.batch_embed_documents"


def test_process_document_logic(document_tasks):
    """
    Call the task's underlying function directly — tests business logic,
    not Celery's broker/backend infrastructure.
    This is the correct unit-test approach: test what the task DOES,
    not how Celery schedules it.
    """
    result = document_tasks.process_document.run(
        document_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
    )
    assert result["status"] == "ready"


def test_delete_chunks_logic(document_tasks):
    result = document_tasks.delete_document_chunks.run(
        document_id=str(uuid.uuid4()),
    )
    assert result["chunks_deleted"] is True


def test_cleanup_logic(ai_tasks):
    result = ai_tasks.cleanup_old_results.run()
    assert result["status"] == "cleaned"


def test_batch_embed_empty_list(ai_tasks):
    result = ai_tasks.batch_embed_documents.run(
        document_ids=[],
        user_id=str(uuid.uuid4()),
    )
    assert result["results"] == []


def test_batch_embed_multiple_documents(ai_tasks):
    doc_ids = [str(uuid.uuid4()) for _ in range(3)]
    result = ai_tasks.batch_embed_documents.run(
        document_ids=doc_ids,
        user_id=str(uuid.uuid4()),
    )
    assert len(result["results"]) == 3


def test_generate_summary_logic(ai_tasks):
    result = ai_tasks.generate_document_summary.run(
        document_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
    )
    assert "document_id" in result
