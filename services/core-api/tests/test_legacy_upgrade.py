"""A database from before migrations converts to the template model in one go."""

import json
import tempfile
from pathlib import Path

from lattice_core import legacy_upgrade
from sqlalchemy import create_engine, inspect, text

_SCHEMA = (Path(__file__).parent / "legacy_schema.sql").read_text()
_NOW = "2025-06-01 10:00:00.000000"


def _legacy_db() -> str:
    path = tempfile.mkstemp(suffix=".sqlite3")[1]
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        ddl = "\n".join(line for line in _SCHEMA.splitlines() if not line.startswith("--"))
        for stmt in ddl.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))

        def ins(table, **row):
            cols = ", ".join(row)
            vals = ", ".join(f":{k}" for k in row)
            conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), row)

        ins("users", id=1, email="admin@lattice.io", full_name="Admin", hashed_password="x",
            role="manager", is_active=1, created_at=_NOW, login_hint_visible=0)
        ins("users", id=2, email="dana@lattice.io", full_name="Dana", hashed_password="x",
            role="editor", is_active=1, created_at=_NOW, login_hint_visible=1,
            login_hint_password="pw")
        ins("locations", id=1, name="Desiccator A", x=10, y=10)
        ins("locations", id=2, name="Lab", x=50, y=50)
        ins("locations", id=3, name="Shelf 7", x=60, y=60)
        ins("catalog_options", id=1, category="project", value="Falcon", active=1,
            sort_order=0, created_at=_NOW)
        common = dict(is_template=0, created_at=_NOW, updated_at=_NOW, quantity=1)
        ins("items", id=10, type="setup", name="Rig", state="working", location_id=2,
            project="Falcon", team="Integration", **common)
        ins("items", id=11, type="card", name="Power Board", state="production",
            card_type="company", serial="PB-1", version="1.2", production_date="2025-03-01",
            responsible="Dana", storage_status="assembled", parent_id=10, location_id=2,
            **common)
        ins("items", id=12, type="card", name="Power Board", state="faulty",
            card_type="company", serial="PB-2", storage_status="desiccator", location_id=3,
            **common)
        ins("items", id=13, type="card", name="NIC", state="used", card_type="commercial",
            storage_status="in_use", location_id=2, industry="Space",
            **{**common, "quantity": 7})
        ins("items", id=14, type="card", name="Power Board", state="production",
            card_type="company", description="Standard board", **{**common, "is_template": 1})
        ins("item_managers", item_id=10, user_id=1)
        ins("state_history", id=1, item_id=12, state="faulty", note="burnt",
            changed_by=1, changed_at=_NOW)
        ins("documents", id=1, item_id=11, name="Spec", url="https://x/spec.pdf")
        ins("documents", id=2, item_id=14, name="Template sheet", url=None)
        ins("extra_items", id=1, setup_id=10, name="PSU")
        ins("change_requests", id=1, action="update", item_id=11, payload=json.dumps({}),
            description="d", reason="r", status="pending", proposed_by=2, created_at=_NOW)
        ins("audit_log", id=1, item_id=11, item_name="Power Board", action="create",
            summary="Created", details=json.dumps({}), user_id=1, created_at=_NOW)
        ins("stock_thresholds", id=1, item_id=11, card_type="company", name="Power Board",
            version=None, min_quantity=3)
    engine.dispose()
    return path


def test_a_pre_migration_database_is_converted():
    path = _legacy_db()
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        assert legacy_upgrade.needs_upgrade(conn)
        legacy_upgrade.run(conn)

    with engine.connect() as conn:
        assert "alembic_version" in inspect(conn).get_table_names()
        assert not legacy_upgrade.needs_upgrade(conn)

        templates = {
            (r.type, r.name): r
            for r in conn.execute(text("SELECT * FROM item_templates")).mappings()
        }
        board = templates[("card", "Power Board")]
        assert board["card_type"] == "house" and board["serial_prefix"] == "POW"
        assert board["description"] == "Standard board", "old template items describe it"
        assert templates[("card", "NIC")]["card_type"] == "commercial"

        items = {
            r.id: r for r in conn.execute(text("SELECT * FROM items")).mappings()
        }
        assert set(items) == {10, 11, 12, 13}, "template items are not items any more"
        assert items[11]["serial"] == "C-POW-001" and items[12]["serial"] == "C-POW-002"
        assert items[10]["serial"].startswith("S-RIG-")
        assert items[11]["parent_id"] == 10
        assert [items[i]["state"] for i in (10, 11, 12, 13)] == ["ok", "built", "faulty", "ok"]
        assert items[13]["quantity"] == 7

        catalog = {
            (r.category, r.value): r.id
            for r in conn.execute(text("SELECT * FROM catalog_options")).mappings()
        }
        assert items[10]["project_id"] == catalog[("project", "Falcon")]
        assert items[10]["team_id"] == catalog[("team", "Integration")]
        assert items[13]["industry_id"] == catalog[("industry", "Space")]

        values = {
            (r.item_id, r.key): r.value
            for r in conn.execute(text(
                "SELECT v.item_id, f.key, v.value FROM item_field_values v "
                "JOIN template_fields f ON f.id = v.field_id"
            )).mappings()
        }
        assert json.loads(values[(11, "legacy_serial")]) == "PB-1"
        assert json.loads(values[(11, "version")]) == "1.2"
        assert json.loads(values[(11, "legacy_responsible")]) == "Dana"

        locs = {r.id: r.is_desiccator for r in conn.execute(text("SELECT * FROM locations"))}
        assert locs[1] and locs[3] and not locs[2], "named or holding desiccator cards"

        cr = conn.execute(text("SELECT status, review_note FROM change_requests")).one()
        assert cr.status == "rejected" and "resubmit" in cr.review_note
        doc = conn.execute(text("SELECT * FROM documents WHERE id = 2")).mappings().one()
        assert doc["item_id"] is None and doc["template_id"] == board["id"]
        threshold = conn.execute(text("SELECT * FROM stock_thresholds")).mappings().one()
        assert threshold["template_id"] == board["id"] and threshold["min_quantity"] == 3
        assert conn.execute(text("SELECT count(*) FROM item_managers")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar() == 1
    engine.dispose()
    Path(path).unlink()


def test_a_fresh_or_current_database_needs_no_conversion(client):
    from lattice_core.database import engine

    with engine.connect() as conn:
        assert not legacy_upgrade.needs_upgrade(conn)
