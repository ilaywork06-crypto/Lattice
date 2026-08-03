"""Idempotent bootstrap: create the schema and the one account needed to sign in.

The system ships **empty**. Nothing here invents projects, locations, items or a
floor plan — a customer's first login lands on a blank system they fill in
themselves. The only row created is the bootstrap administrator, without which
no one could sign in at all.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from lattice_core.config import get_settings
from lattice_core.database import Base, SessionLocal, engine
from lattice_core.models import User, UserRole
from lattice_core.security import hash_password

logger = logging.getLogger("lattice_core.seed")


# Columns added after the first release, as (table, column, DDL type + default).
# The schema comes from ``create_all``, which only ever creates *missing tables*
# — it never touches one that already exists — so a database predating any of
# these would fail on every query for them.
_ADDED_COLUMNS = [
    ("items", "quantity", "INTEGER NOT NULL DEFAULT 1"),
    ("users", "login_hint_visible", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("users", "login_hint_password", "VARCHAR(255)"),
]


def _ensure_columns() -> None:
    """Backfill columns introduced after a database was created. Idempotent."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, ddl in _ADDED_COLUMNS:
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("Added %s.%s to an existing database", table, column)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    with SessionLocal() as db:
        _ensure_admin(db, get_settings())
        db.commit()


def _ensure_admin(db: Session, settings) -> User:
    admin = db.query(User).filter(User.email == settings.bootstrap_admin_email).first()
    if admin is None:
        admin = User(
            email=settings.bootstrap_admin_email,
            full_name="System Administrator",
            hashed_password=hash_password(settings.bootstrap_admin_password),
            role=UserRole.manager,
        )
        db.add(admin)
        db.flush()
        logger.info("Created bootstrap admin %s", admin.email)
    return admin
