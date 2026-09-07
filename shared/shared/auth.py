from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwt

from shared.exceptions import AuthenticationError, AuthorizationError
from shared.models import TokenPayload


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    try:
        # Existing bcrypt hashes may have been created with legacy 72-byte truncation.
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


DEFAULT_SCOPES = (
    "profile:read",
    "ai:invoke",
    "ai:agent",
    "documents:read",
    "documents:write",
    "documents:search",
    "mcp:invoke",
)


def public_key_id(public_key: str) -> str:
    key = serialization.load_pem_public_key(public_key.encode())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise ValueError("An RSA public key of at least 2048 bits is required")
    der = key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:32]


def public_jwk(public_key: str) -> dict[str, str]:
    key = serialization.load_pem_public_key(public_key.encode())
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("RSA public key required")
    numbers = key.public_numbers()

    def encode(number: int) -> str:
        return (
            base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, "big"))
            .rstrip(b"=")
            .decode()
        )

    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": public_key_id(public_key),
        "n": encode(numbers.n),
        "e": encode(numbers.e),
    }


def _create_token(
    user_id: str,
    email: str,
    private_key: str,
    lifetime: timedelta,
    token_type: str,
    issuer: str,
    audience: str,
    scopes: Iterable[str],
) -> str:
    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("An RSA private key of at least 2048 bits is required")
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.UUID(user_id)),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "type": token_type,
        "iss": issuer,
        "aud": audience,
        "jti": str(uuid.uuid4()),
        "scope": " ".join(sorted(set(scopes))),
    }
    return jwt.encode(
        payload, private_key, algorithm="RS256", headers={"kid": public_key_id(public)}
    )


def create_access_token(
    user_id: str,
    email: str,
    private_key: str,
    *,
    expires_minutes: int = 30,
    issuer: str = "http://localhost",
    audience: str = "ai-platform",
    scopes: Iterable[str] = (),
) -> str:
    return _create_token(
        user_id,
        email,
        private_key,
        timedelta(minutes=expires_minutes),
        "access",
        issuer,
        audience,
        scopes,
    )


def create_refresh_token(
    user_id: str,
    email: str,
    private_key: str,
    *,
    expires_days: int = 7,
    issuer: str = "http://localhost",
    audience: str = "ai-platform",
) -> str:
    return _create_token(
        user_id, email, private_key, timedelta(days=expires_days), "refresh", issuer, audience, ()
    )


def decode_token(
    token: str,
    public_key: str,
    *,
    expected_type: Literal["access", "refresh"] = "access",
    issuer: str = "http://localhost",
    audience: str = "ai-platform",
) -> TokenPayload:
    """Validate a fixed algorithm and required claims using public material only."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or header.get("kid") != public_key_id(public_key):
            raise ValueError("Untrusted signing key or algorithm")
        raw = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={
                "require_exp": True,
                "require_iat": True,
                "require_sub": True,
                "require_aud": True,
                "require_iss": True,
            },
        )
        payload = TokenPayload.model_validate(raw, strict=True)
        uuid.UUID(payload.sub)
        uuid.UUID(payload.jti)
        if (
            payload.type != expected_type
            or payload.iat > datetime.now(UTC).timestamp()
            or payload.exp <= payload.iat
        ):
            raise ValueError("Invalid token claims")
        return payload
    except (JWTError, ValueError, TypeError) as exc:
        raise AuthenticationError("Invalid or expired token") from exc


def check_scopes(payload: TokenPayload, *required: str) -> None:
    if not set(required).issubset(payload.scope.split()):
        raise AuthorizationError("Insufficient scope")


def hash_refresh_token(token: str) -> str:
    """Store only a SHA-256 hash of refresh tokens in the DB."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random token string."""
    return secrets.token_urlsafe(nbytes)
