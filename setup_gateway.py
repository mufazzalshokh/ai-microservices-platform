import os

os.makedirs("api-gateway/app/routers", exist_ok=True)
os.makedirs("api-gateway/app/middleware", exist_ok=True)
os.makedirs("api-gateway/app/services", exist_ok=True)

files = {}

# ── api-gateway/Dockerfile ────────────────────────────────────────────────────
files["api-gateway/Dockerfile"] = """\
FROM python:3.11-slim

RUN addgroup --system app && adduser --system --group app

WORKDIR /app

COPY api-gateway/requirements.txt ./requirements.txt
COPY shared/ ./shared/

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e ./shared/

COPY api-gateway/app/ ./app/

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

# ── api-gateway/app/config.py ─────────────────────────────────────────────────
files["api-gateway/app/config.py"] = """\
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "INFO"
    service_name: str = "api-gateway"
    version: str = "0.1.0"

    # Database
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Downstream services
    ai_service_url: str = "http://ai-service:8001"
    document_service_url: str = "http://document-service:8002"


@lru_cache
def get_settings() -> Settings:
    return Settings()
"""

# ── api-gateway/app/database.py ───────────────────────────────────────────────
files["api-gateway/app/database.py"] = """\
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=(settings.environment == "development"),
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    \"\"\"FastAPI dependency: yields an async DB session with auto commit/rollback.\"\"\"
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
"""

# ── api-gateway/app/models.py ─────────────────────────────────────────────────
files["api-gateway/app/models.py"] = """\
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
"""

# ── api-gateway/app/schemas.py ────────────────────────────────────────────────
files["api-gateway/app/schemas.py"] = """\
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from shared.models import AppModel


class RegisterRequest(AppModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(AppModel):
    email: EmailStr
    password: str


class RefreshRequest(AppModel):
    refresh_token: str


class TokenResponse(AppModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(AppModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
"""

# ── api-gateway/app/services/auth_service.py ─────────────────────────────────
files["api-gateway/app/services/auth_service.py"] = """\
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
    \"\"\"All authentication business logic. Routers call this, never touch DB directly.\"\"\"

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
"""

# ── api-gateway/app/middleware/auth.py ────────────────────────────────────────
files["api-gateway/app/middleware/auth.py"] = """\
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.auth import decode_token
from shared.exceptions import AuthenticationError
from shared.models import TokenPayload

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    \"\"\"Dependency for protected endpoints. Raises 401 if token is invalid.\"\"\"
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(
            credentials.credentials,
            settings.jwt_secret_key,
            settings.jwt_algorithm,
            expected_type="access",
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
"""

# ── api-gateway/app/routers/health.py ────────────────────────────────────────
files["api-gateway/app/routers/health.py"] = """\
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import HealthResponse

from app.config import Settings, get_settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthResponse(
        status=overall,
        service=settings.service_name,
        version=settings.version,
        checks=checks,
    )
"""

# ── api-gateway/app/routers/auth.py ──────────────────────────────────────────
files["api-gateway/app/routers/auth.py"] = """\
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
"""

# ── api-gateway/app/main.py ───────────────────────────────────────────────────
files["api-gateway/app/main.py"] = """\
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.exceptions import AppException
from shared.logging import configure_logging, get_logger

from app.config import get_settings
from app.routers import auth, health

settings = get_settings()

configure_logging(level=settings.log_level, service_name=settings.service_name)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "service_starting",
        service=settings.service_name,
        version=settings.version,
        environment=settings.environment,
    )
    yield
    logger.info("service_stopping", service=settings.service_name)


app = FastAPI(
    title="API Gateway",
    description="Authentication and routing for the AI Microservices Platform",
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
app.include_router(auth.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
    }
"""

# ── tests/conftest.py ─────────────────────────────────────────────────────────
files["tests/conftest.py"] = """\
from __future__ import annotations

import os

# Must set env vars BEFORE any app imports
os.environ.setdefault("POSTGRES_USER", "testuser")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")
os.environ.setdefault("POSTGRES_DB", "testdb")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AI_SERVICE_URL", "http://localhost:8001")
os.environ.setdefault("DOCUMENT_SERVICE_URL", "http://localhost:8002")
"""

# ── tests/test_gateway/test_auth.py ──────────────────────────────────────────
files["tests/test_gateway/test_auth.py"] = """\
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def get_client():
    from app.main import app
    return TestClient(app)


def test_health_reachable():
    client = get_client()
    response = client.get("/health")
    assert response.status_code in (200, 503)
    assert "status" in response.json()


def test_register_password_too_short():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "Short1"},
    )
    assert response.status_code == 422


def test_register_password_no_uppercase():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "nouppercase1"},
    )
    assert response.status_code == 422


def test_register_password_no_digit():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "NoDigitPass"},
    )
    assert response.status_code == 422


def test_register_invalid_email():
    client = get_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Password1"},
    )
    assert response.status_code == 422


def test_me_no_token():
    client = get_client()
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_invalid_token():
    client = get_client()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert response.status_code == 401


def test_root_returns_service_info():
    client = get_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "api-gateway"
    assert "docs" in body
"""

# ── Write all files ───────────────────────────────────────────────────────────
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  wrote {path}")

print("\napi-gateway written successfully!")