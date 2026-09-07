from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

from shared.auth import public_key_id


class VerificationSettings(BaseSettings):
    """Resource-server settings deliberately have no private signing key field."""

    jwt_public_key_path: str = "keys/jwt-public.pem"
    jwt_algorithm: Literal["RS256"] = "RS256"
    jwt_issuer: str = "http://localhost"
    jwt_audience: str = "ai-platform"

    @cached_property
    def public_key(self) -> str:
        material = Path(self.jwt_public_key_path).read_text(encoding="utf-8")
        public_key_id(material)
        return material
