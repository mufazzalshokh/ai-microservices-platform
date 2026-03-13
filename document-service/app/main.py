from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.exceptions import AppException
from shared.logging import configure_logging, get_logger

from app.config import get_settings
from app.routers import documents, health

settings = get_settings()
configure_logging(level=settings.log_level, service_name=settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "service_starting",
        service=settings.service_name,
        version=settings.version,
    )
    yield
    logger.info("service_stopping", service=settings.service_name)


app = FastAPI(
    title="Document Service",
    description="File upload, text chunking, vector embeddings and semantic search",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "app_exception",
        status_code=exc.status_code,
        message=exc.message,
        path=str(request.url),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.message, "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "data": None},
    )


app.include_router(health.router)
app.include_router(documents.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
    }
