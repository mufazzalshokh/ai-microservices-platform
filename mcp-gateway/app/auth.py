from mcp.server.auth.provider import AccessToken, TokenVerifier
from shared.auth import decode_token
from shared.exceptions import AuthenticationError

from app.config import Settings


class JWTVerifier(TokenVerifier):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.public_key = settings.public_key

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = decode_token(
                token,
                self.public_key,
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
            )
        except AuthenticationError:
            return None
        return AccessToken(
            token=token,
            client_id="platform-client",
            subject=claims.sub,
            scopes=claims.scope.split(),
            expires_at=claims.exp,
            resource=claims.aud,
        )
