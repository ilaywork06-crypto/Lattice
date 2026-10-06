"""Desiccator-by-location, child-template limits, template duplication and
catalog field groups."""

from alembic import command
from lattice_core.seed import alembic_config
from sqlalchemy import create_engine, text


def _tpl_body(type_, name, prefix, **over):
    body = {"type": type_, "name": name, "serial_prefix": prefix, "fields": []}
    if type_ == "card":
        body["card_type"] = "factory"
    body.update(over)
    return body


def _create_tpl(client, admin, *args, expect=201, **over):
    r = client.post("/templates", json=_tpl_body(*args, **over), headers=admin)
    assert r.status_code == expect, r.text
    return r.json()


def _new(client, admin, template_id, **values):
    r = client.post("/items", json={"template_id": template_id, "values": values},
                    headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _loc(client, admin, name):
    return next(loc for loc in client.get("/locations", headers=admin).json()
                if loc["name"] == name)


# ─────────────────────────── desiccator ───────────────────────────
def test_cards_assembled_in_the_desiccator_still_count(client, admin):
    card = _create_tpl(client, admin, "card", "Desiccator Probe Card", "DPC")
    box = _create_tpl(client, admin, "assembly", "Desiccator Probe Box", "DPB",
                      fields=[{"label": "Location", "field_type": "location"}],
                      children=[{"template_id": card["id"]}])
    desiccator = _loc(client, admin, "Desiccator — Team A")["id"]
    lab = _loc(client, admin, "Lab A — Bench 1")["id"]

    def group():
        return next(g for g in client.get("/inventory/cards", headers=admin).json()
                    if g["template_id"] == card["id"])

    loose = _new(client, admin, card["id"])
    inside = _new(client, admin, card["id"])
    assembly = _new(client, admin, box["id"], location=desiccator)
    r = client.post(f"/items/{inside['id']}/link", json={"parent_id": assembly["id"]},
                    headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["storage_status"] == "desiccator"

    g = group()
    assert (g["desiccator"], g["available"], g["assembled_in_desiccator"]) == (2, 2, 1)
    assert g["assembled"] == 0, "assembled counts only what is outside the desiccator"
    assert sorted(g["available_serials"]) == sorted([loose["serial"], inside["serial"]])

    listed = client.get(f"/items?template_id={card['id']}&storage_status=desiccator",
                        headers=admin).json()
    assert {i["id"] for i in listed} == {loose["id"], inside["id"]}

    # The assembly leaves the desiccator: the card inside goes with it.
    client.post(f"/items/{assembly['id']}/move", json={"location_id": lab}, headers=admin)
    g = group()
    assert (g["desiccator"], g["available"], g["assembled"]) == (1, 1, 1)
    listed = client.get(f"/items?template_id={card['id']}&storage_status=assembled",
                        headers=admin).json()
    assert [i["id"] for i in listed] == [inside["id"]]


# ─────────────────────────── child limits ───────────────────────────
def test_assembly_templates_limit_how_many_cards_of_a_template_they_hold(client, admin):
    card = _create_tpl(client, admin, "card", "Limit Card", "LMC")
    other = _create_tpl(client, admin, "card", "Free Card", "FRC")
    box = _create_tpl(client, admin, "assembly", "Limit Box", "LMB", children=[
        {"template_id": card["id"], "min_count": 1, "max_count": 2},
        {"template_id": other["id"]},
    ])
    assert [(c["template"]["id"], c["min_count"], c["max_count"]) for c in box["children"]] == [
        (card["id"], 1, 2), (other["id"], 0, None),
    ]
    assert box["child_template_ids"] == [card["id"], other["id"]]

    assembly = _new(client, admin, box["id"])
    assert assembly["is_complete"] is False
    row = assembly["composition"][0]
    assert (row["count"], row["missing"], row["is_full"]) == (0, 1, False)
    listed = next(i for i in client.get(f"/items?template_id={box['id']}", headers=admin).json()
                  if i["id"] == assembly["id"])
    assert listed["missing_children"] == 1

    cards = [_new(client, admin, card["id"]) for _ in range(4)]
    for c in cards[:2]:
        r = client.post(f"/items/{c['id']}/link", json={"parent_id": assembly["id"]},
                        headers=admin)
        assert r.status_code == 200, r.text
    detail = client.get(f"/items/{assembly['id']}", headers=admin).json()
    assert detail["is_complete"] is True and detail["composition"][0]["is_full"] is True

    r = client.post(f"/items/{cards[2]['id']}/link", json={"parent_id": assembly["id"]},
                    headers=admin)
    assert r.status_code == 400 and "at most 2" in r.json()["detail"]

    # Swapping a card at the maximum is one edit, judged by the end result.
    r = client.put(f"/items/{assembly['id']}/children",
                   json={"child_ids": [cards[0]["id"], cards[2]["id"]]}, headers=admin)
    assert r.status_code == 200, r.text
    r = client.put(f"/items/{assembly['id']}/children",
                   json={"child_ids": [c["id"] for c in cards[:3]]}, headers=admin)
    assert r.status_code == 400

    # Creating with too many children is refused as a whole.
    r = client.post("/items", json={"template_id": box["id"],
                                    "child_ids": [cards[1]["id"], cards[3]["id"]]},
                    headers=admin)
    assert r.status_code == 201, r.text
    full_id = r.json()["id"]

    # A destroyed card takes no place …
    client.post(f"/items/{cards[1]['id']}/state", json={"state": "destroyed", "note": "x"},
                headers=admin)
    spare = _new(client, admin, card["id"])
    r = client.post(f"/items/{spare['id']}/link", json={"parent_id": full_id}, headers=admin)
    assert r.status_code == 200, r.text
    # … so it can't come back into service while the box is full.
    r = client.post(f"/items/{cards[1]['id']}/state", json={"state": "built", "note": "x"},
                    headers=admin)
    assert r.status_code == 400

    # The maximum cannot drop below what an item already holds.
    r = client.patch(f"/templates/{box['id']}", json={"children": [
        {"template_id": card["id"], "min_count": 0, "max_count": 1},
        {"template_id": other["id"]},
    ]}, headers=admin)
    assert r.status_code == 400 and "already holds 2" in r.json()["detail"]

    # The older id-only form keeps the limits it doesn't mention.
    r = client.patch(f"/templates/{box['id']}",
                     json={"child_template_ids": [card["id"], other["id"]]}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["children"][0]["max_count"] == 2

    for bad in ({"min_count": 3, "max_count": 2}, {"max_count": 0}, {"min_count": -1}):
        r = client.patch(f"/templates/{box['id']}", json={"children": [
            {"template_id": card["id"], **bad}]}, headers=admin)
        assert r.status_code in (400, 422), (bad, r.text)


def test_child_limits_survive_the_migration(tmp_path):
    """A database at 0001 with contents rows upgrades to "no limits"."""
    db_path = tmp_path / "upgrade.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "0001")
        conn.execute(text(
            "INSERT INTO item_templates (id, type, name, card_type, serial_prefix, "
            "created_at, updated_at) VALUES "
            "(1, 'assembly', 'Box', NULL, 'BOX', '2026-01-01', '2026-01-01'), "
            "(2, 'card', 'Card', 'house', 'CRD', '2026-01-01', '2026-01-01')"
        ))
        conn.execute(text(
            "INSERT INTO template_children (parent_template_id, child_template_id) "
            "VALUES (1, 2)"
        ))
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
        row = conn.execute(text(
            "SELECT min_count, max_count FROM template_children"
        )).one()
    assert tuple(row) == (0, None)
    engine.dispose()


# ─────────────────────────── duplication ───────────────────────────
def test_a_template_can_be_duplicated_with_its_shared_files(client, admin):
    src = _create_tpl(client, admin, "card", "Dup Source", "DPS", fields=[
        {"label": "Manual", "field_type": "files", "mode": "fixed"},
        {"label": "Rev", "field_type": "string", "required": True},
    ])
    manual = src["fields"][0]
    r = client.post(f"/templates/{src['id']}/fields/{manual['id']}/files",
                    files={"file": ("manual.pdf", b"%PDF manual", "application/pdf")},
                    headers=admin)
    assert r.status_code == 201, r.text
    original_doc = r.json()

    fields = [
        {"label": f["label"], "field_type": f["field_type"], "mode": f["mode"],
         "required": f["required"], "config": f["config"], "fixed_value": f["fixed_value"],
         **({"copy_files_from": f["id"]} if f["field_type"] == "files" else {})}
        for f in src["fields"]
    ]
    fields.append({"label": "Extra note", "field_type": "text"})
    copy = _create_tpl(client, admin, "card", "Dup Copy", "DPY", fields=fields,
                       source_template_id=src["id"])
    assert [f["label"] for f in copy["fields"]] == ["Manual", "Rev", "Extra note"]
    files = copy["fields"][0]["files"]
    assert len(files) == 1 and files[0]["id"] != original_doc["id"]
    dl = client.get(f"/documents/{files[0]['id']}/download", headers=admin)
    assert dl.content == b"%PDF manual"

    # The copy is independent: deleting it leaves the source's file in place.
    assert client.delete(f"/templates/{copy['id']}", headers=admin).status_code == 204
    dl = client.get(f"/documents/{original_doc['id']}/download", headers=admin)
    assert dl.status_code == 200 and dl.content == b"%PDF manual"


# ─────────────────────────── field groups ───────────────────────────
def test_field_groups_are_reusable_sets_of_fields(client, admin, editor, viewer):
    loc = client.post("/locations", json={"name": "Group Probe Room", "x": 5, "y": 5},
                      headers=admin).json()
    body = {
        "name": "Traceability",
        "description": "What every board records",
        "fields": [
            {"label": "Production date", "field_type": "date", "required": True},
            {"label": "Board ID", "field_type": "serial_string",
             "config": {"pattern": "XX-#####"}},
            {"label": "Where", "field_type": "location", "mode": "choice",
             "config": {"options": [loc["id"]]}},
        ],
    }
    assert client.post("/field-groups", json=body, headers=editor).status_code == 403
    r = client.post("/field-groups", json=body, headers=admin)
    assert r.status_code == 201, r.text
    group = r.json()
    assert [f["key"] for f in group["fields"]] == ["production_date", "board_id", "where"]
    assert group["fields"][2]["options_display"] == ["Group Probe Room"]

    assert client.post("/field-groups", json=body, headers=admin).status_code == 400
    bad = {"name": "Broken", "fields": [{"label": "Format", "field_type": "string",
                                        "config": {"pattern": "XX"}}]}
    assert client.post("/field-groups", json=bad, headers=admin).status_code == 400
    assert client.post("/field-groups", json={"name": "Empty", "fields": []},
                       headers=admin).status_code == 400

    # Everyone can read and search (by name, description or field name).
    found = client.get("/field-groups?search=board id", headers=viewer).json()
    assert [g["name"] for g in found] == ["Traceability"]
    assert client.get("/field-groups?search=nothing-like-it", headers=viewer).json() == []

    r = client.patch(f"/field-groups/{group['id']}", json={
        "name": "Traceability v2",
        "fields": [*body["fields"], {"label": "Notes", "field_type": "text"}],
    }, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Traceability v2" and len(r.json()["fields"]) == 4

    # The fields load straight into a new template.
    fields = [{k: f[k] for k in ("label", "field_type", "mode", "required", "config")}
              for f in r.json()["fields"]]
    tpl = _create_tpl(client, admin, "card", "From A Group", "FAG", fields=fields)
    assert len(tpl["fields"]) == 4

    # A deleted location disappears from the group's lists as well.
    assert client.delete(f"/locations/{loc['id']}", headers=admin).status_code == 204
    g = client.get(f"/field-groups/{group['id']}", headers=admin).json()
    assert g["fields"][2]["config"]["options"] == []

    assert client.delete(f"/field-groups/{group['id']}", headers=viewer).status_code == 403
    assert client.delete(f"/field-groups/{group['id']}", headers=admin).status_code == 204
    assert client.get(f"/field-groups/{group['id']}", headers=admin).status_code == 404
    # The template made from it is unaffected.
    assert len(client.get(f"/templates/{tpl['id']}", headers=admin).json()["fields"]) == 4



def test_removing_and_reordering_children_keeps_the_rest(client, admin):
    a = _create_tpl(client, admin, "card", "Child A", "CHA")
    b = _create_tpl(client, admin, "card", "Child B", "CHB")
    box = _create_tpl(client, admin, "assembly", "Child Box", "CHX", children=[
        {"template_id": a["id"], "min_count": 1}, {"template_id": b["id"], "max_count": 3},
    ])
    r = client.patch(f"/templates/{box['id']}", json={"children": [
        {"template_id": b["id"], "max_count": 4},
    ]}, headers=admin)
    assert r.status_code == 200, r.text
    assert [(c["template"]["id"], c["max_count"]) for c in r.json()["children"]] == [(b["id"], 4)]
    assert r.json()["child_template_ids"] == [b["id"]]
    assert box["id"] not in client.get(f"/templates/{a['id']}", headers=admin).json()[
        "parent_template_ids"]
    # A removed template can no longer be linked in.
    box_item = _new(client, admin, box["id"])
    card = _new(client, admin, a["id"])
    r = client.post(f"/items/{card['id']}/link", json={"parent_id": box_item["id"]},
                    headers=admin)
    assert r.status_code == 400


def test_a_card_inside_a_container_without_a_location_leaves_the_desiccator(client, admin):
    card = _create_tpl(client, admin, "card", "Nowhere Card", "NWC")
    box = _create_tpl(client, admin, "assembly", "Nowhere Box", "NWB",
                      children=[{"template_id": card["id"]}])
    c = _new(client, admin, card["id"])
    assert c["storage_status"] == "desiccator"
    b = _new(client, admin, box["id"])  # no location
    r = client.post(f"/items/{c['id']}/link", json={"parent_id": b["id"]}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["location_id"] is None and r.json()["storage_status"] == "assembled"


def test_moving_a_container_re_checks_the_stock_of_its_cards(client, admin, monkeypatch):
    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr("lattice_core.events.publish_event", fake_publish)
    card = _create_tpl(client, admin, "card", "Alert Card", "ALC")
    box = _create_tpl(client, admin, "assembly", "Alert Box", "ALB",
                      fields=[{"label": "Location", "field_type": "location"}],
                      children=[{"template_id": card["id"]}])
    desiccator = _loc(client, admin, "Desiccator — Team A")["id"]
    lab = _loc(client, admin, "Lab A — Bench 1")["id"]
    b = _new(client, admin, box["id"], location=desiccator)
    c = _new(client, admin, card["id"])
    client.post(f"/items/{c['id']}/link", json={"parent_id": b["id"]}, headers=admin)
    client.post("/inventory/thresholds", json={"template_id": card["id"], "min_quantity": 0},
                headers=admin)
    published.clear()
    client.post(f"/items/{b['id']}/move", json={"location_id": lab}, headers=admin)
    comps = [c for e in published if e.type.value == "inventory.low_stock"
             for c in e.payload["components"]]
    assert any(x["template_id"] == card["id"] for x in comps)
