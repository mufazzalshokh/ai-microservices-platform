from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.exceptions import NotFoundError, ValidationError
from shared.logging import get_logger

from app.config import Settings
from app.models import Document, DocumentChunk
from app.schemas import DocumentResponse, SearchResult
from app.services.chunker import chunk_text, extract_text_from_bytes
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

# Max file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


class DocumentService:
    """Orchestrates document upload, chunking, embedding, and search."""

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._vector_store = VectorStore(db=db, settings=settings)

    async def upload_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> Document:
        """
        Full upload pipeline:
        1. Validate file
        2. Create document record (status=pending)
        3. Extract text
        4. Chunk text
        5. Generate embeddings + store chunks
        6. Update status to ready (or failed)
        """
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValidationError(
                f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB"
            )

        # Step 1: Create document record
        document = Document(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            status="pending",
        )
        self._db.add(document)
        await self._db.flush()  # get the ID

        logger.info(
            "document_upload_started",
            document_id=str(document.id),
            filename=filename,
            size_bytes=len(file_bytes),
        )

        try:
            # Step 2: Extract text
            text = extract_text_from_bytes(file_bytes, content_type)

            if not text.strip():
                document.status = "failed"
                logger.warning(
                    "document_no_text_extracted",
                    document_id=str(document.id),
                    content_type=content_type,
                )
                return document

            # Step 3: Chunk
            document.status = "processing"
            chunks = chunk_text(
                text,
                chunk_size=self._settings.chunk_size,
                overlap=self._settings.chunk_overlap,
            )

            logger.info(
                "document_chunked",
                document_id=str(document.id),
                num_chunks=len(chunks),
            )

            # Step 4: Embed + store
            await self._vector_store.embed_and_store(document, chunks)

            document.status = "ready"
            logger.info(
                "document_upload_complete",
                document_id=str(document.id),
                num_chunks=len(chunks),
            )

        except Exception as exc:
            document.status = "failed"
            logger.error(
                "document_upload_failed",
                document_id=str(document.id),
                error=str(exc),
            )
            raise

        return document

    async def list_documents(self, user_id: uuid.UUID) -> list[Document]:
        """Return all documents belonging to a user."""
        result = await self._db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document(self, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
        """Get a single document, verifying ownership."""
        document = await self._db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        if not document:
            raise NotFoundError("Document")
        return document

    async def delete_document(self, document_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete document and all its chunks (cascade handles DB side)."""
        document = await self.get_document(document_id, user_id)
        await self._db.delete(document)
        logger.info("document_deleted", document_id=str(document_id))

    async def search(
        self,
        query: str,
        user_id: uuid.UUID,
        limit: int = 5,
        document_id: uuid.UUID | None = None,
    ) -> list[SearchResult]:
        """Semantic search across user's documents."""
        return await self._vector_store.search(
            query=query,
            user_id=user_id,
            limit=limit,
            document_id=document_id,
        )
