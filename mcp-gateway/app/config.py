from functools import lru_cache

from pydantic_settings import SettingsConfigDict
from shared.config import VerificationSettings


class Settings(VerificationSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    document_service_url: str = "http://document-service:8002"
    mcp_resource_url: str = "http://localhost/mcp"
    mcp_allowed_hosts: list[str] = [
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "mcp-gateway:8003",
    ]
    mcp_allowed_origins: list[str] = [
        "http://localhost",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ]
    downstream_timeout_seconds: float = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
