"""Fixtures for the notification-service (throwaway SQLite, no Redis/SMTP needed)."""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import jwt
import pytest

_db_fd, _db_path = tempfile.mkstemp(suffix=".sqlite3")
os.environ["NOTIFY_DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "a-test-secret-value-at-least-32-bytes-long"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # consumer backs off; harmless

from fastapi.testclient import TestClient  # noqa: E402
from lattice_notifications.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    os.close(_db_fd)
    if os.path.exists(_db_path):
        os.remove(_db_path)


def _token_for(user_id: int, role: str = "manager") -> dict:
    now = datetime.now(UTC)
    tok = jwt.encode(
        {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(hours=1)},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def token_for():
    return _token_for
