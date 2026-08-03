"""Pytest fixtures — spin the API up against a throwaway SQLite DB.

The product ships **empty**: ``seed.py`` creates the bootstrap admin and nothing
else. So the little world these tests read — users, catalogs, locations, a setup
with an assembly and cards, thresholds, a floor plan — is built here instead.
Fixtures own their data; shipped code never invents rows to keep a test green.
"""

import os
import tempfile
from datetime import date

import pytest

# Must be set BEFORE importing lattice_core (engine is built at import time).
_db_fd, _db_path = tempfile.mkstemp(suffix=".sqlite3")
os.environ["CORE_DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # publish fails silently in tests

from fastapi.testclient import TestClient  # noqa: E402
from lattice_core.database import SessionLocal  # noqa: E402
from lattice_core.main import app  # noqa: E402
from lattice_core.models import (  # noqa: E402
    CardType,
    CatalogCategory,
    CatalogOption,
    ChangeAction,
    Document,
    ExtraItem,
    ItemState,
    ItemType,
    Location,
    MapBuilding,
    StockThreshold,
    StorageStatus,
    User,
    UserRole,
)
from lattice_core.security import hash_password  # noqa: E402
from lattice_core.services import change_requests as cr_svc  # noqa: E402
from lattice_core.services import items as item_svc  # noqa: E402

_BUILDINGS = [
    ("Lab A", 4, 6, 40, 38, "#5b6ef5"),
    ("Assembly Hall", 48, 6, 48, 24, "#26a69a"),
    ("Storage", 48, 34, 22, 26, "#e6a532"),
    ("Desiccator Room", 74, 34, 22, 26, "#42a5f5"),
    ("Lab B", 4, 48, 40, 46, "#7e57c2"),
    ("Offices", 48, 64, 48, 30, "#8a8f9a"),
]


def _build_world(db) -> None:
    """One small but complete system: every feature under test has something to
    act on, and nothing is duplicated just to inflate a count."""
    admin = db.query(User).filter(User.role == UserRole.manager).one()

    # ── users (the login page offers these as shortcuts) ──
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
    db.flush()

    # ── admin-managed vocabularies (§2) ──
    db.add_all([
        CatalogOption(category=CatalogCategory.project, value="Falcon", sort_order=1),
        CatalogOption(category=CatalogCategory.project, value="Sparrow", sort_order=2),
        CatalogOption(category=CatalogCategory.project, value="Horizon", sort_order=3),
        CatalogOption(category=CatalogCategory.industry, value="Avionics", sort_order=1),
        CatalogOption(category=CatalogCategory.industry, value="Space", sort_order=2),
        CatalogOption(category=CatalogCategory.industry, value="Defense", sort_order=3),
    ])
    db.add_all([
        MapBuilding(name=n, x=x, y=y, width=w, height=h, color=c, sort_order=i)
        for i, (n, x, y, w, h, c) in enumerate(_BUILDINGS, start=1)
    ])
    db.flush()

    # ── locations (tests move items between ids 1..5) ──
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

    # ── cards: both tracking modes, two versions of one model ──
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

    # ── the hierarchy ──
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

    # a fault + recovery, so state history has something in it
    item_svc.change_state(db, setup, ItemState.faulty, "Power rail dropped in burn-in.", admin)
    item_svc.change_state(db, setup, ItemState.working, "Replaced regulator; retested OK.", noa)

    db.add_all([
        ExtraItem(
            setup_id=setup.id, name="Sealevel serial adapter",
            company_part_number="SL-7205e", serial="SL-11923", signed_by="Dana",
        ),
        ExtraItem(
            setup_id=setup.id, name="EPROM burner",
            company_part_number="BRN-9", serial="BRN-0421", signed_by="Noa",
        ),
        Document(
            item_id=unique_cards[0].id, name="FPGA bring-up test report",
            doc_type="test", url="https://example.local/docs/fpga-bringup.pdf",
        ),
    ])

    # ── stock thresholds: one healthy, two deliberately short ──
    # Each is anchored to a real card (`item_id`), which is what lets an alert
    # link straight to it. `version=None` widens the watch to the whole model.
    db.add_all([
        StockThreshold(
            item_id=company_cards[0].id, card_type=CardType.company,
            name="Power Regulator Board", version=None,
            min_quantity=2, editor_email=dana.email,
        ),
        StockThreshold(
            item_id=unique_cards[0].id, card_type=CardType.unique,
            name="FPGA Processing Core", version="2.0", min_quantity=4,
        ),
        StockThreshold(
            item_id=commercial.id, card_type=CardType.commercial,
            name="COTS Ethernet NIC", version=None,
            min_quantity=6, editor_email=dana.email,
        ),
    ])

    # ── reusable templates (§5) ──
    make(
        type=ItemType.card,
        name="Power Regulator Board",
        is_template=True,
        card_type=CardType.company,
        version="1.3",
        state=ItemState.production,
        project="Falcon",
        industry="Avionics",
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
    )

    # ── a proposal waiting for a manager ──
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


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # context manager runs lifespan → schema + admin
        with SessionLocal() as db:
            _build_world(db)
            db.commit()
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
