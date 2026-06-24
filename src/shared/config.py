from __future__ import annotations

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderType(StrEnum):
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    OPENAI = "openai"


def get_available_provider_and_key() -> tuple[ProviderType, str, str]:
    for provider_type, api_key_attr, model_attr in (
        (ProviderType.DEEPSEEK, "deepseek_api_key", "deepseek_model"),
        (ProviderType.GEMINI, "gemini_api_key", "gemini_model"),
        (ProviderType.CLAUDE, "anthropic_api_key", "anthropic_model"),
        (ProviderType.OPENAI, "openai_api_key", "openai_model"),
    ):
        api_key = getattr(settings, api_key_attr, "")
        if api_key:
            model = getattr(settings, model_attr, "")
            return provider_type, api_key, model
    raise RuntimeError("no LLM provider API key configured")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8080
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ezchess"
    database_ssl: bool = False
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    session_secret: str = "change-me-in-production"
    anthropic_model: str = "claude-sonnet-4-20250514"
    deepseek_model: str = "deepseek-chat"
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4.1"
    session_cookie_name: str = "session_token"
    session_max_age_seconds: int = 86400
    secure_cookie: bool = False
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"
    stockfish_path: str = "/usr/local/bin/stockfish"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672"

    llm_max_retries: int = 3


settings = Settings()
