from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class AppModel(BaseModel):
    """Root base model for all shared models."""
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
    )


class APIResponse(AppModel, Generic[DataT]):
    """Standard envelope for every API response."""
    success: bool = True
    data: DataT | None = None
    message: str = "OK"
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(AppModel, Generic[DataT]):
    """Paginated list response."""
    items: list[DataT]
    total: int
    page: int
    page_size: int
    pages: int


class TokenPayload(AppModel):
    """JWT token payload."""
    sub: str
    email: str
    exp: int
    iat: int
    type: str


class UserPublic(AppModel):
    """Safe user representation - never expose hashed_password."""
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class DocumentPublic(AppModel):
    """Document metadata returned to clients."""
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str | None
    status: str
    created_at: datetime


class HealthResponse(AppModel):
    """Standard health check response for every service."""
    status: str = "ok"
    service: str
    version: str = "0.1.0"
    checks: dict[str, str] = Field(default_factory=dict)
