import os

os.makedirs("shared/shared", exist_ok=True)

files = {}

# ── shared/pyproject.toml ─────────────────────────────────────────────────────
files["shared/pyproject.toml"] = """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "shared"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "structlog>=24.1",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*"]
"""

# ── shared/shared/exceptions.py ───────────────────────────────────────────────
files["shared/shared/exceptions.py"] = """\
from __future__ import annotations


class AppException(Exception):
    \"\"\"Base class for all application exceptions.\"\"\"

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(AppException):
    \"\"\"Raised when JWT is missing, expired, or invalid.\"\"\"

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class AuthorizationError(AppException):
    \"\"\"Raised when user lacks permission for the action.\"\"\"

    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(message, status_code=403)


class NotFoundError(AppException):
    \"\"\"Raised when a requested resource does not exist.\"\"\"

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found", status_code=404)


class ValidationError(AppException):
    \"\"\"Raised when business-level validation fails (not Pydantic).\"\"\"

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class ServiceUnavailableError(AppException):
    \"\"\"Raised when a downstream service cannot be reached.\"\"\"

    def __init__(self, service: str = "Upstream service") -> None:
        super().__init__(f"{service} is unavailable", status_code=503)
"""

# ── shared/shared/models.py ───────────────────────────────────────────────────
files["shared/shared/models.py"] = """\
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class AppModel(BaseModel):
    \"\"\"Root base model for all shared models.\"\"\"
    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
    )


class APIResponse(AppModel, Generic[DataT]):
    \"\"\"Standard envelope for every API response.\"\"\"
    success: bool = True
    data: DataT | None = None
    message: str = "OK"
    meta: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(AppModel, Generic[DataT]):
    \"\"\"Paginated list response.\"\"\"
    items: list[DataT]
    total: int
    page: int
    page_size: int
    pages: int


class TokenPayload(AppModel):
    \"\"\"JWT token payload.\"\"\"
    sub: str
    email: str
    exp: int
    iat: int
    type: str


class UserPublic(AppModel):
    \"\"\"Safe user representation - never expose hashed_password.\"\"\"
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class DocumentPublic(AppModel):
    \"\"\"Document metadata returned to clients.\"\"\"
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str | None
    status: str
    created_at: datetime


class HealthResponse(AppModel):
    \"\"\"Standard health check response for every service.\"\"\"
    status: str = "ok"
    service: str
    version: str = "0.1.0"
    checks: dict[str, str] = Field(default_factory=dict)
"""

# ── shared/shared/auth.py ─────────────────────────────────────────────────────
files["shared/shared/auth.py"] = """\
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from shared.exceptions import AuthenticationError
from shared.models import TokenPayload

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    \"\"\"Hash a plaintext password with bcrypt.\"\"\"
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    \"\"\"Return True if plain matches the bcrypt hash.\"\"\"
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: str,
    email: str,
    secret: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    \"\"\"Create a short-lived JWT access token.\"\"\"
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_refresh_token(
    user_id: str,
    email: str,
    secret: str,
    algorithm: str,
    expires_days: int,
) -> str:
    \"\"\"Create a long-lived JWT refresh token.\"\"\"
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expires_days)).timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(
    token: str,
    secret: str,
    algorithm: str,
    expected_type: Literal["access", "refresh"] = "access",
) -> TokenPayload:
    \"\"\"Decode and validate a JWT. Raises AuthenticationError on any failure.\"\"\"
    try:
        raw = jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    if raw.get("type") != expected_type:
        raise AuthenticationError(
            f"Expected {expected_type} token, got {raw.get('type')}"
        )
    return TokenPayload(**raw)


def hash_refresh_token(token: str) -> str:
    \"\"\"Store only a SHA-256 hash of refresh tokens in the DB.\"\"\"
    return hashlib.sha256(token.encode()).hexdigest()


def generate_secure_token(nbytes: int = 32) -> str:
    \"\"\"Generate a cryptographically secure random token string.\"\"\"
    return secrets.token_urlsafe(nbytes)
"""

# ── shared/shared/logging.py ──────────────────────────────────────────────────
files["shared/shared/logging.py"] = """\
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", service_name: str = "service") -> None:
    \"\"\"Configure structlog for the entire service. Call once at startup.\"\"\"
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.contextvars.merge_contextvars,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    \"\"\"Get a named structured logger.\"\"\"
    return structlog.get_logger(name)
"""

# ── shared/shared/__init__.py ─────────────────────────────────────────────────
files["shared/shared/__init__.py"] = """\
from shared.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from shared.exceptions import (
    AppException,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from shared.logging import configure_logging, get_logger
from shared.models import (
    APIResponse,
    DocumentPublic,
    HealthResponse,
    PaginatedResponse,
    TokenPayload,
    UserPublic,
)

__all__ = [
    "AppException", "AuthenticationError", "AuthorizationError",
    "NotFoundError", "ServiceUnavailableError", "ValidationError",
    "create_access_token", "create_refresh_token", "decode_token",
    "hash_password", "hash_refresh_token", "verify_password",
    "configure_logging", "get_logger",
    "APIResponse", "DocumentPublic", "HealthResponse",
    "PaginatedResponse", "TokenPayload", "UserPublic",
]
"""

# ── Write all files ───────────────────────────────────────────────────────────
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  wrote {path}")

print("\nshared/ library written successfully!")