from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared.auth import check_scopes, decode_token
from shared.exceptions import AuthenticationError, AuthorizationError
from shared.models import TokenPayload

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    """Identical JWT verification as api-gateway — shared secret."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(
            credentials.credentials,
            settings.public_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expected_type="access",
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_scopes(*scopes: str):
    async def dependency(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
        try:
            check_scopes(payload, *scopes)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail="Insufficient scope") from exc
        return payload
    return dependency
