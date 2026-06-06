from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    session_secret: str = "change-me-in-production"
    anthropic_model: str = "claude-sonnet-4-20250514"
    deepseek_model: str = "deepseek-chat"
    session_cookie_name: str = "session_token"
    session_max_age_seconds: int = 86400
    secure_cookie: bool = False
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"
    stockfish_path: str = "/usr/local/bin/stockfish"


settings = Settings()
