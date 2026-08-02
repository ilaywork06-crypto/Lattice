"""Idempotent bootstrap: create schema, an admin user and (optionally) demo data."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from lattice_core.config import get_settings
from lattice_core.database import Base, SessionLocal, engine
from lattice_core.models import (
    CardType,
    CatalogCategory,
    CatalogOption,
    ChangeAction,
    ItemState,
    ItemType,
    Location,
    MapBuilding,
    StockThreshold,
    StorageStatus,
    User,
    UserRole,
)
from lattice_core.security import hash_password
from lattice_core.services import change_requests as cr_svc
from lattice_core.services import items as item_svc

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
    settings = get_settings()
    with SessionLocal() as db:
        admin = _ensure_admin(db, settings)
        if settings.seed_demo_data and db.query(User).count() <= 1:
            _seed_demo(db, admin)
        if settings.seed_demo_data:
            _ensure_map_buildings(db)
        db.commit()


# The floor-plan background is seeded on its own, not as part of `_seed_demo`:
# that only runs on a virgin database, so databases created before the map
# existed would otherwise be stuck with a blank plan forever.
_DEFAULT_BUILDINGS = [
    ("Lab A", 4, 6, 40, 38, "#5b6ef5"),
    ("Assembly Hall", 48, 6, 48, 24, "#26a69a"),
    ("Storage", 48, 34, 22, 26, "#e6a532"),
    ("Desiccator Room", 74, 34, 22, 26, "#42a5f5"),
    ("Lab B", 4, 48, 40, 46, "#7e57c2"),
    ("Offices", 48, 64, 48, 30, "#8a8f9a"),
]


def _ensure_map_buildings(db: Session) -> None:
    """Lay down the default floor-plan when there isn't one.

    Guarded on the table being empty rather than per-name: a per-name check
    would resurrect buildings the user deliberately deleted on every restart.
    The trade-off is that emptying the plan completely re-seeds it next boot.
    """
    if db.query(MapBuilding).count():
        return
    db.add_all([
        MapBuilding(name=n, x=x, y=y, width=w, height=h, color=c, sort_order=i)
        for i, (n, x, y, w, h, c) in enumerate(_DEFAULT_BUILDINGS, start=1)
    ])
    db.flush()
    logger.info("Seeded %d default floor-plan buildings", len(_DEFAULT_BUILDINGS))


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


def _seed_demo(db: Session, admin: User) -> None:
    logger.info("Seeding demo data …")

    # ── users ──
    # `login_hint_*` publishes these on the sign-in screen. It is set here, in
    # the demo-only path, and never by `_ensure_admin` — a real deployment must
    # not put its bootstrap admin's password on a public page. Managers can
    # retire any of these shortcuts from Users & Permissions.
    noa = User(
        email="noa@lattice.io",
        full_name="Noa (Team Lead)",
        hashed_password=hash_password("password"),
        role=UserRole.manager,
        login_hint_visible=True,
        login_hint_password="password",
    )
    dana = User(
        email="dana@lattice.io",
        full_name="Dana (Editor)",
        hashed_password=hash_password("password"),
        role=UserRole.editor,
        login_hint_visible=True,
        login_hint_password="password",
    )
    amir = User(
        email="amir@lattice.io",
        full_name="Amir (Viewer)",
        hashed_password=hash_password("password"),
        role=UserRole.viewer,
        login_hint_visible=True,
        login_hint_password="password",
    )
    db.add_all([noa, dana, amir])
    admin.login_hint_visible = True
    admin.login_hint_password = get_settings().bootstrap_admin_password
    db.flush()

    # ── admin-managed catalogs (§2): items may only use these values ──
    db.add_all([
        CatalogOption(category=CatalogCategory.project, value="Falcon", sort_order=1),
        CatalogOption(category=CatalogCategory.project, value="Sparrow", sort_order=2),
        CatalogOption(category=CatalogCategory.project, value="Horizon", sort_order=3),
        CatalogOption(category=CatalogCategory.industry, value="Avionics", sort_order=1),
        CatalogOption(category=CatalogCategory.industry, value="Space", sort_order=2),
        CatalogOption(category=CatalogCategory.industry, value="Defense", sort_order=3),
    ])
    db.flush()

    # ── locations (x/y are 0..100 on the POC floor-plan map) ──
    locs = {
        "lab_a": Location(name="Lab A — Bench 1", building="B1", room="101", x=22, y=30),
        "lab_b": Location(name="Lab B — Bench 4", building="B1", room="105", x=48, y=26),
        "integration": Location(
            name="Integration Hall", building="B2", room="Hall", x=70, y=55
        ),
        "desiccator": Location(
            name="Desiccator — Team A", building="B1", room="Storage", x=30, y=72
        ),
        "storage": Location(name="Storage Room", building="B2", room="S1", x=80, y=80),
    }
    db.add_all(locs.values())
    db.flush()

    def make(**kw):
        kw.setdefault("manager_ids", [])
        return item_svc.create_item(db, kw, admin)

    # ── cards ──
    # Kept deliberately small: one example of each case worth seeing, not a
    # warehouse. Serialised boards across two versions (so the version/date
    # breakdown has something to break down), a couple of unique cards, and a
    # single quantity-tracked commercial row.
    company_cards = [
        make(
            type=ItemType.card,
            name="Power Regulator Board",
            card_type=CardType.company,
            version="1.2",
            production_date=date(2025, 3, 1),
            state=ItemState.built,
            storage_status=StorageStatus.desiccator,
            location_id=locs["desiccator"].id,
            project="Falcon",
            industry="Avionics",
            responsible="Dana",
            lead="Noa",
            serial=f"PRB-{i:03d}",
        )
        for i in range(1, 4)
    ]
    company_cards.append(
        make(
            type=ItemType.card,
            name="Power Regulator Board",
            card_type=CardType.company,
            version="1.3",
            production_date=date(2025, 6, 15),
            state=ItemState.built,
            storage_status=StorageStatus.desiccator,
            location_id=locs["desiccator"].id,
            project="Falcon",
            industry="Avionics",
            serial="PRB13-001",
        )
    )

    unique_cards = [
        make(
            type=ItemType.card,
            name="FPGA Processing Core",
            card_type=CardType.unique,
            version="2.0",
            production_date=date(2025, 2, 10),
            state=ItemState.working,
            storage_status=StorageStatus.desiccator,
            location_id=locs["desiccator"].id,
            project="Falcon",
            industry="Avionics",
            responsible="Noa",
            lead="Noa",
            serial=f"FPGA-2024-{i:04d}",
        )
        for i in range(1, 3)
    ]

    # A commercial card is a *quantity* of interchangeable parts on one row —
    # no serial, no six near-identical rows to count by hand (§12).
    commercial = make(
        type=ItemType.card,
        name="COTS Ethernet NIC",
        card_type=CardType.commercial,
        quantity=4,
        state=ItemState.working,
        storage_status=StorageStatus.in_use,
        location_id=locs["storage"].id,
        project="Falcon",
    )

    # ── assembly (1 unique + 1 company) ──
    assembly = make(
        type=ItemType.assembly,
        name="Signal Processing Module",
        state=ItemState.built,
        location_id=locs["lab_a"].id,
        project="Falcon",
        industry="Avionics",
        team="HW-Team-A",
        description="Small assembly: 1 unique FPGA core + 1 power board.",
        dmz="Rev B, conformal-coated.",
    )
    item_svc.link_item(db, unique_cards[0], assembly, admin)
    item_svc.link_item(db, company_cards[0], assembly, admin)

    # ── setup (contains the assembly + more cards) ──
    setup = make(
        type=ItemType.setup,
        name="Falcon Test Setup #1",
        state=ItemState.working,
        location_id=locs["integration"].id,
        project="Falcon",
        industry="Avionics",
        team="Integration",
        description="Large setup for running the Falcon software stack.",
        dmz="Full DAMATZ: 1x SPM assembly, 1x company card, 4x NIC.",
        manager_ids=[noa.id],
    )
    item_svc.link_item(db, assembly, setup, admin)
    item_svc.link_item(db, company_cards[1], setup, admin)
    item_svc.link_item(db, commercial, setup, admin)
    # unique_cards[1] and the remaining boards stay in the desiccator on purpose:
    # with the demo this small, every card group needs stock left in there for
    # /inventory/desiccator to have anything to show.

    # a fault + recovery to populate state history
    item_svc.change_state(
        db, setup, ItemState.faulty, "Power rail dropped during burn-in test.", admin
    )
    item_svc.change_state(
        db, setup, ItemState.working, "Replaced regulator board; retested OK.", noa
    )

    # ── extra (non-card) items inside the setup ──
    from lattice_core.models import ExtraItem

    db.add_all([
        ExtraItem(
            setup_id=setup.id,
            name="Sealevel serial adapter",
            company_part_number="SL-7205e",
            serial="SL-11923",
            signed_by="Dana",
        ),
        ExtraItem(
            setup_id=setup.id,
            name="EPROM burner",
            company_part_number="BRN-9",
            serial="BRN-0421",
            signed_by="Noa",
        ),
    ])

    # ── documents on a card ──
    from lattice_core.models import Document

    db.add(
        Document(
            item_id=unique_cards[0].id,
            name="FPGA bring-up test report",
            doc_type="test",
            url="https://example.local/docs/fpga-bringup.pdf",
        )
    )

    # ── stock threshold (company card min qty) ──
    db.add(
        StockThreshold(
            card_type=CardType.company,
            name="Power Regulator Board",
            min_quantity=2,  # comfortably stocked — the healthy row for contrast
            editor_email=dana.email,
        )
    )
    db.add(
        StockThreshold(
            card_type=CardType.unique,
            name="FPGA Processing Core",
            min_quantity=4,  # deliberately triggers a low-stock alert in the demo
        )
    )
    db.add(
        StockThreshold(
            card_type=CardType.commercial,
            name="COTS Ethernet NIC",
            min_quantity=6,  # 4 in stock → a second component in the same digest
            editor_email=dana.email,
        )
    )

    # ── reusable templates (§5): blueprints to spin up new items fast ──
    make(
        type=ItemType.card,
        name="Power Regulator Board",
        is_template=True,
        card_type=CardType.company,
        version="1.3",
        state=ItemState.production,
        project="Falcon",
        industry="Avionics",
        responsible="Dana",
        lead="Noa",
        description="Standard company power board — duplicate and set the serial.",
    )
    make(
        type=ItemType.setup,
        name="Falcon Test Setup",
        is_template=True,
        state=ItemState.production,
        project="Falcon",
        industry="Avionics",
        team="Integration",
        description="Blueprint for a Falcon integration bench.",
    )

    # ── a pending change request from the editor ──
    db.flush()
    cr_svc.create_change_request(
        db,
        {
            "action": ChangeAction.state_change.value,
            "item_id": assembly.id,
            "payload": {"state": ItemState.used.value, "note": "Moved to field use."},
            "description": "Set the Signal Processing Module state to 'used'.",
            "reason": "It has been deployed into the field setup.",
        },
        dana,
    )

    logger.info("Demo data seeded.")
