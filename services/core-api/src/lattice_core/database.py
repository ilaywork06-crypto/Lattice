"""SQLAlchemy engine, session factory and declarative Base."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from lattice_core.config import get_settings

settings = get_settings()

_IS_SQLITE = settings.core_database_url.startswith("sqlite")

# SQLite needs check_same_thread=False when used with FastAPI's threadpool.
_connect_args = {"check_same_thread": False} if _IS_SQLITE else {}

engine = create_engine(
    settings.core_database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

if _IS_SQLITE:
    # SQLite ignores ON DELETE rules (and every FK) unless asked per connection,
    # which would let the dev/test database drift from Postgres' behaviour.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Deterministic constraint names, so migrations can address (drop/alter) them
# on every backend — SQLite's batch mode in particular needs a name to find one.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
