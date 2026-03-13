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
    service_name: str = "document-service"
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

    # JWT (for verifying tokens issued by api-gateway)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"

    # OpenAI (for generating embeddings)
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimensions: int = 1536

    # Chunking config
    chunk_size: int = 500        # characters per chunk
    chunk_overlap: int = 50      # overlap between chunks


@lru_cache
def get_settings() -> Settings:
    return Settings()
