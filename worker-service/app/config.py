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
    service_name: str = "worker-service"
    version: str = "0.1.0"

    # Redis — Celery broker AND result backend
    redis_url: str = "redis://redis:6379/0"

    # Database — for reading/writing document status
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        # Sync SQLAlchemy URL for Celery tasks (Celery is sync by default)
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # OpenAI
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-ada-002"

    # Service URLs (for calling other services via HTTP)
    ai_service_url: str = "http://ai-service:8001"
    document_service_url: str = "http://document-service:8002"

    # Task config
    task_max_retries: int = 3
    task_retry_backoff: int = 60  # seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()
