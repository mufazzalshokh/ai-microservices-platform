from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions import AppException
from shared.models import APIResponse, TokenPayload

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.auth import require_auth
from app.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db=db, settings=settings)


def _raise(exc: AppException) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(_get_service),
) -> APIResponse[UserResponse]:
    try:
        user = await service.register(payload)
        return APIResponse(
            data=UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                created_at=user.created_at,
            ),
            message="User registered successfully",
        )
    except AppException as exc:
        _raise(exc)


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    summary="Login and receive JWT tokens",
)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(_get_service),
) -> APIResponse[TokenResponse]:
    try:
        tokens = await service.login(payload)
        return APIResponse(data=tokens, message="Login successful")
    except AppException as exc:
        _raise(exc)


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    summary="Refresh access token",
)
async def refresh_token(
    payload: RefreshRequest,
    service: AuthService = Depends(_get_service),
) -> APIResponse[TokenResponse]:
    try:
        tokens = await service.refresh(payload.refresh_token)
        return APIResponse(data=tokens, message="Token refreshed")
    except AppException as exc:
        _raise(exc)


@router.post(
    "/logout",
    response_model=APIResponse[None],
    summary="Logout and invalidate refresh token",
)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(_get_service),
) -> APIResponse[None]:
    await service.logout(payload.refresh_token)
    return APIResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get current authenticated user",
)
async def me(
    token_payload: TokenPayload = Depends(require_auth),
    service: AuthService = Depends(_get_service),
) -> APIResponse[UserResponse]:
    try:
        user = await service.get_current_user(token_payload.sub)
        return APIResponse(
            data=UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                created_at=user.created_at,
            )
        )
    except AppException as exc:
        _raise(exc)
