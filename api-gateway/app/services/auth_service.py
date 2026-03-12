from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from shared.exceptions import AuthenticationError, NotFoundError, ValidationError
from shared.logging import get_logger

from app.config import Settings
from app.models import RefreshToken, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse

logger = get_logger(__name__)


class AuthService:
    """All authentication business logic. Routers call this, never touch DB directly."""

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def register(self, payload: RegisterRequest) -> User:
        existing = await self._db.scalar(
            select(User).where(User.email == payload.email)
        )
        if existing:
            raise ValidationError(f"Email {payload.email} is already registered")

        user = User(
            email=payload.email,
            hashed_password=hash_password(payload.password),
        )
        self._db.add(user)
        await self._db.flush()

        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self._db.scalar(
            select(User).where(User.email == payload.email)
        )
        if not user or not verify_password(payload.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        tokens = await self._create_token_pair(user)
        logger.info("user_login", user_id=str(user.id))
        return tokens

    async def refresh(self, refresh_token_str: str) -> TokenResponse:
        payload = decode_token(
            refresh_token_str,
            self._settings.jwt_secret_key,
            self._settings.jwt_algorithm,
            expected_type="refresh",
        )

        token_hash = hash_refresh_token(refresh_token_str)
        stored = await self._db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if not stored:
            raise AuthenticationError("Refresh token not found or already used")

        if stored.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise AuthenticationError("Refresh token has expired")

        await self._db.delete(stored)

        user = await self._db.get(User, uuid.UUID(payload.sub))
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        tokens = await self._create_token_pair(user)
        logger.info("token_refreshed", user_id=str(user.id))
        return tokens

    async def logout(self, refresh_token_str: str) -> None:
        token_hash = hash_refresh_token(refresh_token_str)
        stored = await self._db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if stored:
            await self._db.delete(stored)
            logger.info("user_logout", user_id=str(stored.user_id))

    async def get_current_user(self, user_id: str) -> User:
        user = await self._db.get(User, uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User")
        return user

    async def _create_token_pair(self, user: User) -> TokenResponse:
        user_id_str = str(user.id)
        access_token = create_access_token(
            user_id=user_id_str,
            email=user.email,
            secret=self._settings.jwt_secret_key,
            algorithm=self._settings.jwt_algorithm,
            expires_minutes=self._settings.jwt_access_token_expire_minutes,
        )
        refresh_token = create_refresh_token(
            user_id=user_id_str,
            email=user.email,
            secret=self._settings.jwt_secret_key,
            algorithm=self._settings.jwt_algorithm,
            expires_days=self._settings.jwt_refresh_token_expire_days,
        )
        expires_at = datetime.now(UTC) + timedelta(
            days=self._settings.jwt_refresh_token_expire_days
        )
        self._db.add(RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=expires_at,
        ))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )
