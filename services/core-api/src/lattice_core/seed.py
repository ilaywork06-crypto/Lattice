"""Idempotent bootstrap: bring the schema to head and create the one account
needed to sign in.

The system ships **empty**. Nothing here invents projects, locations, items or a
floor plan — a customer's first login lands on a blank system they fill in
themselves. The only row created is the bootstrap administrator, without which
no one could sign in at all.

The schema is owned by Alembic (``lattice_core/migrations``). A database created
before migrations existed is converted once by ``legacy_upgrade`` and then
carries on like any other.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from lattice_core.config import get_settings
from lattice_core.database import SessionLocal, engine
from lattice_core.models import User, UserRole
from lattice_core.security import hash_password

logger = logging.getLogger("lattice_core.seed")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(connection: Connection | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        # Run on the caller's connection/transaction (no URL parsing involved).
        cfg.attributes["connection"] = connection
    return cfg


def upgrade_schema(connection: Connection) -> None:
    command.upgrade(alembic_config(connection), "head")


def init_db() -> None:
    from lattice_core import legacy_upgrade

    with engine.begin() as conn:
        if legacy_upgrade.needs_upgrade(conn):
            legacy_upgrade.run(conn)
        else:
            upgrade_schema(conn)
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
