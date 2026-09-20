from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mock_mode: bool = True

    dashscope_api_key: str = ""
    qwen_model: str = "qwen-plus"

    openweather_api_key: str = ""

    map_mcp_url: str = "http://localhost:8811/mcp"
    map_mcp_api_key: str = ""

    jwt_secret: str = "change-me-to-a-random-string-at-least-32-bytes-long"
    jwt_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    checkpoint_db_path: str = "./data/checkpoints.sqlite3"
    idempotency_db_path: str = "./data/idempotency.sqlite3"

    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
