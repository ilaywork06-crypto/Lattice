"""Pytest fixtures — spin the API up against a throwaway SQLite DB.

The product ships **empty**: ``seed.py`` creates the bootstrap admin and nothing
else. So the little world these tests read — users, catalogs, locations, the
desiccator, templates, a setup with an assembly and cards, thresholds, a floor
plan — is built here instead. Fixtures own their data; shipped code never
invents rows to keep a test green.
"""

import os
import tempfile

import pytest

# Must be set BEFORE importing lattice_core (engine is built at import time).
# LATTICE_TEST_DATABASE_URL runs the suite against another (empty) database —
# e.g. PostgreSQL, which is what production uses.
_db_fd, _db_path = tempfile.mkstemp(suffix=".sqlite3")
_upload_dir = tempfile.mkdtemp(prefix="lattice-uploads-")
os.environ["CORE_DATABASE_URL"] = os.environ.get(
    "LATTICE_TEST_DATABASE_URL", f"sqlite:///{_db_path}"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # publish fails silently in tests
os.environ["UPLOAD_DIR"] = _upload_dir

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
    FieldMode,
    FieldType,
    ItemState,
    Location,
    MapBuilding,
    StockThreshold,
    User,
    UserRole,
)
from lattice_core.security import hash_password  # noqa: E402
from lattice_core.services import catalog as catalog_svc  # noqa: E402
from lattice_core.services import change_requests as cr_svc  # noqa: E402
from lattice_core.services import items as item_svc  # noqa: E402
from lattice_core.services import templates as tpl_svc  # noqa: E402

_BUILDINGS = [
    ("Lab A", 4, 6, 40, 38, "#5b6ef5"),
    ("Assembly Hall", 48, 6, 48, 24, "#26a69a"),
    ("Storage", 48, 34, 22, 26, "#e6a532"),
    ("Desiccator Room", 74, 34, 22, 26, "#42a5f5"),
]


def field(label, field_type, mode=FieldMode.item, required=False, **extra):
    return {
        "label": label,
        "field_type": field_type.value,
        "mode": mode.value,
        "required": required,
        **extra,
    }


def _build_world(db) -> None:
    """One small but complete system: every feature under test has something to
    act on, and nothing is duplicated just to inflate a count."""
    admin = db.query(User).filter(User.role == UserRole.manager).one()

    # ── users (the login page offers these as shortcuts) ──
    def user(email, name, role):
        return User(
            email=email, full_name=name, hashed_password=hash_password("password"),
            role=role, login_hint_visible=True, login_hint_password="password",
        )

    noa = user("noa@lattice.io", "Noa (Team Lead)", UserRole.manager)
    dana = user("dana@lattice.io", "Dana (Editor)", UserRole.editor)
    amir = user("amir@lattice.io", "Amir (Viewer)", UserRole.viewer)
    db.add_all([noa, dana, amir])
    db.flush()

    # ── catalogs: projects, industries, teams — and links between them ──
    opts = {}
    for category, values in (
        (CatalogCategory.project, ["Falcon", "Sparrow", "Horizon"]),
        (CatalogCategory.industry, ["Avionics", "Space", "Defense"]),
        (CatalogCategory.team, ["HW-Team-A", "Integration"]),
    ):
        for i, v in enumerate(values, start=1):
            o = CatalogOption(category=category, value=v, sort_order=i)
            db.add(o)
            opts[v] = o
    db.flush()
    catalog_svc.link(db, opts["HW-Team-A"].id, opts["Avionics"].id)
    catalog_svc.link(db, opts["HW-Team-A"].id, opts["Falcon"].id)
    catalog_svc.link(db, opts["Integration"].id, opts["Falcon"].id)

    db.add_all([
        MapBuilding(name=n, x=x, y=y, width=w, height=h, color=c, sort_order=i)
        for i, (n, x, y, w, h, c) in enumerate(_BUILDINGS, start=1)
    ])

    # ── locations (two make up the desiccator) ──
    locs = {
        "lab_a": Location(name="Lab A — Bench 1", building="B1", room="101", x=22, y=30),
        "lab_b": Location(name="Lab B — Bench 4", building="B1", room="105", x=48, y=26),
        "integration": Location(name="Integration Hall", building="B2", x=70, y=55),
        "desiccator": Location(name="Desiccator — Team A", building="B1", x=30, y=72,
                               is_desiccator=True),
        "desiccator_b": Location(name="Desiccator — Team B", building="B1", x=34, y=72,
                                 is_desiccator=True),
        "storage": Location(name="Storage Room", building="B2", room="S1", x=80, y=80),
    }
    db.add_all(locs.values())
    db.flush()

    # ── card templates ──
    prb_t = tpl_svc.create_template(db, {
        "type": "card", "name": "Power Regulator Board", "card_type": CardType.house.value,
        "serial_prefix": "PRB",
        "fields": [
            field("Project", FieldType.project, FieldMode.fixed, True,
                  fixed_value=opts["Falcon"].id),
            field("Industry", FieldType.industry, FieldMode.fixed, fixed_value=opts["Avionics"].id),
            field("Version", FieldType.enum, FieldMode.choice, True,
                  config={"options": ["1.3", "1.2"]}),
            field("Production date", FieldType.date),
            field("Responsible", FieldType.responsible),
            field("Managers", FieldType.managers, FieldMode.fixed, fixed_value=[noa.id]),
            field("Location", FieldType.location),
            field("Status", FieldType.status, FieldMode.choice,
                  config={"options": ["built", "ok"]}),
        ],
    }, admin)
    fpga_t = tpl_svc.create_template(db, {
        "type": "card", "name": "FPGA Processing Core", "card_type": CardType.copied.value,
        "serial_prefix": "FPG",
        "fields": [
            field("Description", FieldType.description, required=True,
                  config={"min_length": 8}),
            field("Board ID", FieldType.serial_string, config={"pattern": "FP-#####"}),
            field("Letter", FieldType.letter),
            field("Datasheet", FieldType.files),
        ],
    }, admin)
    nic_t = tpl_svc.create_template(db, {
        "type": "card", "name": "COTS Ethernet NIC", "card_type": CardType.commercial.value,
        "serial_prefix": "NIC",
        "fields": [
            field("Quantity", FieldType.quantity, required=True),
            field("Vendor link", FieldType.link),
        ],
    }, admin)

    # ── container templates ──
    spm_t = tpl_svc.create_template(db, {
        "type": "assembly", "name": "Signal Processing Module", "serial_prefix": "SPM",
        "fields": [
            field("Team", FieldType.team, FieldMode.fixed, fixed_value=opts["HW-Team-A"].id),
            field("Rev", FieldType.string),
            field("Location", FieldType.location),
        ],
        "child_template_ids": [prb_t.id, fpga_t.id],
    }, admin)
    setup_t = tpl_svc.create_template(db, {
        "type": "setup", "name": "Falcon Test Setup", "serial_prefix": "FTS",
        "fields": [
            field("Project", FieldType.project, FieldMode.fixed, fixed_value=opts["Falcon"].id),
            field("Managers", FieldType.managers, FieldMode.fixed, fixed_value=[noa.id]),
            field("Location", FieldType.location, required=True),
            field("Notes", FieldType.text),
        ],
        "child_template_ids": [spm_t.id, prb_t.id, nic_t.id],
    }, admin)

    def make(tpl, **values):
        return item_svc.create_item(db, {"template_id": tpl.id, "values": values}, admin)

    # ── cards: 3 PRB in the desiccator, 2 FPGA, 1 NIC stock row of 4 ──
    prbs = [make(prb_t, version="1.3") for _ in range(3)]
    prbs.append(make(prb_t, version="1.2", location=locs["storage"].id))  # in use, not stock
    fpgas = [
        make(fpga_t, description="FPGA core, rev B silicon", board_id="12345")
        for _ in range(2)
    ]
    make(nic_t, quantity=4)

    # ── the hierarchy ──
    spm = make(spm_t, rev="B", location=locs["lab_a"].id)
    item_svc.link_item(db, fpgas[0], spm, admin)
    item_svc.link_item(db, prbs[0], spm, admin)

    setup = make(setup_t, location=locs["integration"].id, notes="Main rig")
    item_svc.link_item(db, spm, setup, admin)
    item_svc.link_item(db, prbs[1], setup, admin)

    # a fault + recovery, so state history has something in it
    item_svc.change_state(db, setup, ItemState.faulty, "Power rail dropped in burn-in.", admin)
    item_svc.change_state(db, setup, ItemState.ok, "Replaced regulator; retested OK.", noa)

    db.add_all([
        ExtraItem(setup_id=setup.id, name="Sealevel serial adapter",
                  company_part_number="SL-7205e", serial="SL-11923", signed_by="Dana"),
        Document(item_id=fpgas[0].id, name="FPGA bring-up test report", doc_type="test",
                 url="https://example.local/docs/fpga-bringup.pdf"),
        # thresholds: PRB has 1 available unit (≤2 → low); NIC has 4 ≥ 3 (healthy)
        StockThreshold(template_id=prb_t.id, min_quantity=2, editor_email=dana.email),
        StockThreshold(template_id=nic_t.id, min_quantity=3),
    ])

    # ── a proposal waiting for a manager ──
    db.flush()
    cr_svc.create_change_request(
        db,
        {
            "action": ChangeAction.state_change.value,
            "item_id": spm.id,
            "payload": {"state": ItemState.ok.value, "note": "Tested."},
            "reason": "It passed the bench test.",
        },
        dana,
    )


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # context manager runs lifespan → migrations + admin
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
def templates(client, admin):
    """Template id by serial prefix."""
    return {t["serial_prefix"]: t["id"] for t in client.get("/templates", headers=admin).json()}


@pytest.fixture(scope="session")
def a_setup(client, admin):
    items = client.get("/items?type=setup", headers=admin).json()
    return items[0]["id"]
