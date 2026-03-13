from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.models import HealthResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """
    AI service health check.
    Note: we don't call OpenAI here — that costs money.
    We just confirm the service is up and config is loaded.
    """
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        checks={"config": "ok", "openai_key_set": str(bool(settings.openai_api_key))},
    )
