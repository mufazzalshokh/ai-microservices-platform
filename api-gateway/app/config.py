from __future__ import annotations

from functools import cached_property, lru_cache

from pydantic_settings import SettingsConfigDict
from shared.config import VerificationSettings


class Settings(VerificationSettings):
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

    # JWT signing material belongs only to the issuer.
    jwt_private_key_path: str = "keys/jwt-private.pem"

    @cached_property
    def private_key(self) -> str:
        from pathlib import Path

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from shared.auth import public_key_id
        material = Path(self.jwt_private_key_path).read_text(encoding="utf-8")
        key = serialization.load_pem_private_key(material.encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("RSA private key required")
        public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        if public_key_id(public) != public_key_id(self.public_key):
            raise ValueError("Signing and verification keys do not match")
        return material

    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Downstream services
    ai_service_url: str = "http://ai-service:8001"
    document_service_url: str = "http://document-service:8002"


@lru_cache
def get_settings() -> Settings:
    return Settings()
