from __future__ import annotations

import uuid

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

from app.config import Settings
from app.models import Document, DocumentChunk
from app.schemas import SearchResult

logger = get_logger(__name__)


class VectorStore:
    """
    Manages embedding generation and vector similarity search.
    Uses pgvector for storage and cosine similarity for search.
    """

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def embed_and_store(
        self,
        document: Document,
        chunks: list[str],
    ) -> list[DocumentChunk]:
        """
        Generate embeddings for all chunks and persist them.
        Uses OpenAI batch embedding for efficiency.
        """
        if not chunks:
            return []

        logger.info(
            "embedding_chunks",
            document_id=str(document.id),
            num_chunks=len(chunks),
        )

        # Generate all embeddings in one API call (much cheaper than N calls)
        embeddings = await self._generate_embeddings(chunks)

        db_chunks: list[DocumentChunk] = []
        for idx, (content, embedding) in enumerate(zip(chunks, embeddings)):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                content=content,
                embedding=embedding,
            )
            self._db.add(chunk)
            db_chunks.append(chunk)

        await self._db.flush()

        logger.info(
            "chunks_stored",
            document_id=str(document.id),
            num_chunks=len(db_chunks),
        )
        return db_chunks

    async def search(
        self,
        query: str,
        user_id: uuid.UUID,
        limit: int = 5,
        document_id: uuid.UUID | None = None,
    ) -> list[SearchResult]:
        """
        Semantic similarity search across user's documents.
        Returns chunks ordered by cosine similarity to the query.
        """
        query_embedding = await self._generate_embeddings([query])
        embedding_str = str(query_embedding[0])

        # Build the SQL query using pgvector's <=> (cosine distance) operator
        # 1 - distance = similarity score
        if document_id:
            sql = text("""
                SELECT
                    dc.id          AS chunk_id,
                    dc.document_id,
                    d.filename,
                    dc.chunk_index,
                    dc.content,
                    1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.user_id = :user_id
                  AND dc.document_id = :document_id
                  AND dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """)
            params = {
                "embedding": embedding_str,
                "user_id": str(user_id),
                "document_id": str(document_id),
                "limit": limit,
            }
        else:
            sql = text("""
                SELECT
                    dc.id          AS chunk_id,
                    dc.document_id,
                    d.filename,
                    dc.chunk_index,
                    dc.content,
                    1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.user_id = :user_id
                  AND dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """)
            params = {
                "embedding": embedding_str,
                "user_id": str(user_id),
                "limit": limit,
            }

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                filename=row.filename,
                chunk_index=row.chunk_index,
                content=row.content,
                similarity=float(row.similarity),
            )
            for row in rows
        ]

    async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI embeddings API. Returns list of float vectors."""
        response = await self._client.embeddings.create(
            input=texts,
            model=self._settings.embedding_model,
        )
        return [item.embedding for item in response.data]
