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
    service_name: str = "ai-service"
    version: str = "0.1.0"

    # JWT (verify tokens issued by api-gateway)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"

    # LLM
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Generation defaults
    max_tokens: int = 1024
    temperature: float = 0.7
    max_prompt_length: int = 8000   # chars — guard against token abuse


@lru_cache
def get_settings() -> Settings:
    return Settings()
