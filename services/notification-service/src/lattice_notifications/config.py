"""Runtime configuration, loaded from environment / .env via pydantic-settings.

Mirrors ``lattice_core.config`` so the two services feel consistent. Field names
map to upper-case env vars (e.g. ``notify_database_url`` ← ``NOTIFY_DATABASE_URL``).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — defaults to a local SQLite file so the service can boot without
    # Postgres. docker-compose overrides NOTIFY_DATABASE_URL with the Postgres DSN.
    notify_database_url: str = "sqlite:///./lattice_notify.sqlite3"

    # Event bus (Redis pub/sub) — same instance core-api publishes to.
    redis_url: str = "redis://localhost:6379/0"

    # Auth — MUST match core-api so we validate the same JWTs. The default here
    # deliberately equals core-api's default so dev works without any env.
    jwt_secret: str = "dev-insecure-secret-change-me-please-32b+"
    jwt_algorithm: str = "HS256"

    # Outbound email (MailHog in dev: no auth, no TLS).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "lattice@lattice.io"
    smtp_use_tls: bool = False

    # CORS (frontend origins). The localhost regex in main.py additionally
    # allows any http://localhost:<port> so the browser frontend can call us.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
