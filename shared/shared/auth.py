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
    """Hash a plaintext password with bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: str,
    email: str,
    secret: str,
    algorithm: str,
    expires_minutes: int,
) -> str:
    """Create a short-lived JWT access token."""
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
    """Create a long-lived JWT refresh token."""
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
    """Decode and validate a JWT. Raises AuthenticationError on any failure."""
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
    """Store only a SHA-256 hash of refresh tokens in the DB."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random token string."""
    return secrets.token_urlsafe(nbytes)
