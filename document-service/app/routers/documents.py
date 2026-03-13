from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions import AppException
from shared.models import APIResponse, TokenPayload

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.schemas import DocumentResponse, SearchRequest, SearchResult
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentService:
    return DocumentService(db=db, settings=settings)


def _raise(exc: AppException) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/upload",
    response_model=APIResponse[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for processing and embedding",
)
async def upload_document(
    file: UploadFile = File(...),
    token: TokenPayload = Depends(require_auth),
    service: DocumentService = Depends(_get_service),
) -> APIResponse[DocumentResponse]:
    """
    Upload a text file. The service will:
    1. Extract text content
    2. Split into overlapping chunks
    3. Generate vector embeddings via OpenAI
    4. Store chunks + embeddings in pgvector
    """
    try:
        file_bytes = await file.read()
        document = await service.upload_document(
            user_id=uuid.UUID(token.sub),
            filename=file.filename or "unknown",
            content_type=file.content_type or "text/plain",
            file_bytes=file_bytes,
        )
        return APIResponse(
            data=DocumentResponse(
                id=document.id,
                user_id=document.user_id,
                filename=document.filename,
                content_type=document.content_type,
                status=document.status,
                created_at=document.created_at,
            ),
            message="Document uploaded and processed",
        )
    except AppException as exc:
        _raise(exc)


@router.get(
    "/",
    response_model=APIResponse[list[DocumentResponse]],
    summary="List all documents for the authenticated user",
)
async def list_documents(
    token: TokenPayload = Depends(require_auth),
    service: DocumentService = Depends(_get_service),
) -> APIResponse[list[DocumentResponse]]:
    documents = await service.list_documents(uuid.UUID(token.sub))
    return APIResponse(
        data=[
            DocumentResponse(
                id=d.id,
                user_id=d.user_id,
                filename=d.filename,
                content_type=d.content_type,
                status=d.status,
                created_at=d.created_at,
            )
            for d in documents
        ]
    )


@router.get(
    "/{document_id}",
    response_model=APIResponse[DocumentResponse],
    summary="Get a single document by ID",
)
async def get_document(
    document_id: uuid.UUID,
    token: TokenPayload = Depends(require_auth),
    service: DocumentService = Depends(_get_service),
) -> APIResponse[DocumentResponse]:
    try:
        doc = await service.get_document(document_id, uuid.UUID(token.sub))
        return APIResponse(
            data=DocumentResponse(
                id=doc.id,
                user_id=doc.user_id,
                filename=doc.filename,
                content_type=doc.content_type,
                status=doc.status,
                created_at=doc.created_at,
            )
        )
    except AppException as exc:
        _raise(exc)


@router.delete(
    "/{document_id}",
    response_model=APIResponse[None],
    summary="Delete a document and all its chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    token: TokenPayload = Depends(require_auth),
    service: DocumentService = Depends(_get_service),
) -> APIResponse[None]:
    try:
        await service.delete_document(document_id, uuid.UUID(token.sub))
        return APIResponse(message="Document deleted")
    except AppException as exc:
        _raise(exc)


@router.post(
    "/search",
    response_model=APIResponse[list[SearchResult]],
    summary="Semantic search across your documents",
)
async def search_documents(
    payload: SearchRequest,
    token: TokenPayload = Depends(require_auth),
    service: DocumentService = Depends(_get_service),
) -> APIResponse[list[SearchResult]]:
    """
    Find document chunks most semantically similar to the query.
    Uses pgvector cosine similarity on OpenAI embeddings.
    """
    try:
        results = await service.search(
            query=payload.query,
            user_id=uuid.UUID(token.sub),
            limit=payload.limit,
            document_id=payload.document_id,
        )
        return APIResponse(data=results, message=f"Found {len(results)} results")
    except AppException as exc:
        _raise(exc)
