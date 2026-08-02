"""SQLAlchemy engine, session factory and declarative Base.

Mirrors ``lattice_core.database`` (including the SQLite ``check_same_thread``
handling) so the two services behave the same.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from lattice_notifications.config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False when used with FastAPI's threadpool
# (and with the background consumer task, which writes from another thread).
_connect_args = (
    {"check_same_thread": False}
    if settings.notify_database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.notify_database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist. Import models so they register."""
    from lattice_notifications import models  # noqa: F401  (registers mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Add columns introduced after the table was first created.

    ``create_all`` never alters an existing table, so a database from before
    ``notifications.payload`` existed would break on every read. Idempotent.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "notifications" not in inspector.get_table_names():
        return
    if "payload" in {c["name"] for c in inspector.get_columns("notifications")}:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE notifications ADD COLUMN payload JSON"))
