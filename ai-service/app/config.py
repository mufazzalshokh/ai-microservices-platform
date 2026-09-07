from __future__ import annotations

from functools import lru_cache

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
    service_name: str = "ai-service"
    version: str = "0.1.0"

    # JWT (verify tokens issued by api-gateway)

    # LLM
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Document assistant
    mcp_url: str = "http://mcp-gateway:8003/mcp"
    agent_model: str = "gpt-4o-mini"
    agent_timeout_seconds: float = 60

    # Generation defaults
    max_tokens: int = 1024
    temperature: float = 0.7
    max_prompt_length: int = 8000   # chars — guard against token abuse


@lru_cache
def get_settings() -> Settings:
    return Settings()
