from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Raised on startup when required config is missing for the selected provider mode."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: PostgresDsn = Field(..., alias="DATABASE_URL")
    redis_url: RedisDsn = Field(..., alias="REDIS_URL")

    # LLM providers — OpenAI is always required; others only for multi mode
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")

    # Provider mode
    provider_mode: Literal["multi", "openai_only"] = Field(
        default="openai_only", alias="PROVIDER_MODE"
    )

    # Tools
    tavily_api_key: str = Field(..., alias="TAVILY_API_KEY")

    # Vector DB
    pinecone_api_key: str = Field(..., alias="PINECONE_API_KEY")
    pinecone_index: str = Field(default="nexus-memory", alias="PINECONE_INDEX")

    # Auth
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600

    # Sandbox
    sandbox_url: str = Field(default="sandbox:50051", alias="SANDBOX_URL")

    # Observability
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    @model_validator(mode="after")
    def _validate_multi_provider_keys(self) -> Settings:
        if self.provider_mode == "multi":
            if not self.anthropic_api_key:
                raise ConfigurationError(
                    "PROVIDER_MODE is 'multi' but ANTHROPIC_API_KEY is not set. "
                    "Either set the key or set PROVIDER_MODE=openai_only."
                )
            if not self.google_api_key:
                raise ConfigurationError(
                    "PROVIDER_MODE is 'multi' but GOOGLE_API_KEY is not set. "
                    "Either set the key or set PROVIDER_MODE=openai_only."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
