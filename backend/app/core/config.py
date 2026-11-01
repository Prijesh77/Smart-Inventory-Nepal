"""Application settings, read from environment variables or the project's .env file.

Secrets (database password, later the JWT key) never appear in code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str
    sql_echo: bool = False

    # Login tokens. Set JWT_SECRET_KEY in .env (see .env.example). If it is
    # missing, a random key is generated at start-up: fine for development,
    # but everyone is logged out whenever the server restarts.
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
