from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: PostgresDsn = Field(..., alias="DATABASE_URL")
    redis_url: RedisDsn = Field(..., alias="REDIS_URL")

    # LLM providers
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    google_api_key: str = Field(..., alias="GOOGLE_API_KEY")

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
