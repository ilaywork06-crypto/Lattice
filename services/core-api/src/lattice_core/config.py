"""Runtime configuration, loaded from environment / .env via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — defaults to a local SQLite file so the API can boot without
    # Postgres (handy for tests / quick smoke runs). docker-compose overrides
    # CORE_DATABASE_URL with the Postgres DSN.
    core_database_url: str = "sqlite:///./lattice_core.sqlite3"

    # Event bus
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "dev-insecure-secret-change-me-please-32b+"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # Bootstrap admin + demo data
    bootstrap_admin_email: str = "admin@lattice.io"
    bootstrap_admin_password: str = "admin1234"
    seed_demo_data: bool = True

    # CORS (frontend origins)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
