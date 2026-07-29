"""Pytest fixtures — spin the API up against a throwaway SQLite DB."""

import os
import tempfile

import pytest

# Must be set BEFORE importing lattice_core (engine is built at import time).
_db_fd, _db_path = tempfile.mkstemp(suffix=".sqlite3")
os.environ["CORE_DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # publish fails silently in tests

from fastapi.testclient import TestClient  # noqa: E402
from lattice_core.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # context manager runs lifespan → seeding
        yield c
    os.close(_db_fd)
    if os.path.exists(_db_path):
        os.remove(_db_path)


def _token(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _token(client, "admin@lattice.io", "admin1234")


@pytest.fixture(scope="session")
def manager(client):
    return _token(client, "noa@lattice.io", "password")


@pytest.fixture(scope="session")
def editor(client):
    return _token(client, "dana@lattice.io", "password")


@pytest.fixture(scope="session")
def viewer(client):
    return _token(client, "amir@lattice.io", "password")


@pytest.fixture(scope="session")
def a_setup(client, admin):
    items = client.get("/items?type=setup", headers=admin).json()
    return items[0]["id"]
