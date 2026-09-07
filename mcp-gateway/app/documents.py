import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class DownstreamError(Exception):
    """Contains only a fixed, safe message suitable for a tool response."""


class DocumentMetadata(BaseModel):
    id: UUID
    user_id: UUID
    filename: str
    content_type: str | None
    status: str
    created_at: datetime


class SearchHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    chunk_index: int = Field(ge=0)
    content: str
    similarity: float


class DocumentClient:
    def __init__(self, base_url: str, timeout: float, transport: httpx.AsyncBaseTransport | None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def call(
        self, token: str, *, search: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        path = "/api/v1/documents/search" if search is not None else "/api/v1/documents/"
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(
                    timeout=self.timeout,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST" if search is not None else "GET",
                    self.base_url + path,
                    headers={"Authorization": f"Bearer {token}"},
                    json=search,
                ) as response,
            ):
                if response.status_code == 401:
                    raise DownstreamError("Unauthorized: downstream credential rejected")
                if response.status_code == 403:
                    raise DownstreamError("Forbidden: downstream scope denied")
                if response.status_code != 200:
                    raise DownstreamError("Document service unavailable")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        raise DownstreamError("Document response exceeds size limit")
            import json

            envelope = json.loads(body)
            if not isinstance(envelope, dict) or envelope.get("success") is not True:
                raise DownstreamError("Invalid document response")
            if search is not None:
                hits = TypeAdapter(list[SearchHit]).validate_python(envelope["data"])
                return [hit.model_dump(mode="json") for hit in hits]
            documents = TypeAdapter(list[DocumentMetadata]).validate_python(envelope["data"])
            return [doc.model_dump(mode="json", exclude={"user_id"}) for doc in documents]
        except (httpx.HTTPError, TimeoutError):
            raise DownstreamError("Document service unavailable") from None
        except (ValueError, KeyError, TypeError, ValidationError):
            raise DownstreamError("Invalid document response") from None
