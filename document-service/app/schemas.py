from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from shared.models import AppModel


# ── Response schemas ──────────────────────────────────────────────────────────

class DocumentResponse(AppModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str | None
    status: str
    created_at: datetime


class ChunkResponse(AppModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    created_at: datetime


class SearchRequest(AppModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    document_id: uuid.UUID | None = None   # optionally scope to one document


class SearchResult(AppModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    similarity: float
