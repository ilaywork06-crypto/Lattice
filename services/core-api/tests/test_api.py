"""End-to-end behavioural tests for the Lattice core API."""


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_auth_and_roles(client, viewer):
    me = client.get("/auth/me", headers=viewer).json()
    assert me["role"] == "viewer"


def test_viewer_cannot_mutate(client, viewer, a_setup):
    r = client.post(f"/items/{a_setup}/move", headers=viewer, json={"location_id": 1})
    assert r.status_code == 403


def test_editor_cannot_mutate_directly(client, editor, a_setup):
    r = client.post(f"/items/{a_setup}/move", headers=editor, json={"location_id": 1})
    assert r.status_code == 403


def test_inventory_summary(client, admin):
    s = client.get("/inventory/summary", headers=admin).json()
    assert s["setups"] >= 1 and s["cards"] >= 10
    assert s["cards_desiccator"] >= 1


def test_card_groups_grouped_by_version(client, admin):
    groups = client.get("/inventory/cards", headers=admin).json()
    names = {(g["name"], g["version"]) for g in groups}
    assert ("Power Regulator Board", "1.2") in names
    assert ("Power Regulator Board", "1.3") in names


def test_low_stock_detected(client, admin):
    low = client.get("/inventory/low-stock", headers=admin).json()
    assert any(t["name"] == "FPGA Processing Core" and t["is_low"] for t in low)


def test_state_machine_requires_note_for_fault(client, admin, a_setup):
    r = client.post(f"/items/{a_setup}/state", headers=admin, json={"state": "faulty"})
    assert r.status_code == 400  # no note → rejected

    ok = client.post(
        f"/items/{a_setup}/state",
        headers=admin,
        json={"state": "faulty", "note": "PSU failed"},
    )
    assert ok.status_code == 200
    # restore
    client.post(
        f"/items/{a_setup}/state",
        headers=admin,
        json={"state": "working", "note": "fixed"},
    )


def test_move_cascades_to_children(client, admin, manager, a_setup):
    # link rule check first
    detail = client.get(f"/items/{a_setup}", headers=admin).json()
    assert len(detail["children"]) >= 1

    client.post(f"/items/{a_setup}/move", headers=admin, json={"location_id": 2})
    after = client.get(f"/items/{a_setup}", headers=admin).json()
    assert after["location_id"] == 2
    for child in after["children"]:
        assert child["location_id"] == 2


def test_link_rules_enforced(client, admin):
    # a setup cannot become a child of anything
    setups = client.get("/items?type=setup", headers=admin).json()
    cards = client.get("/items?type=card", headers=admin).json()
    r = client.post(
        f"/items/{setups[0]['id']}/link",
        headers=admin,
        json={"parent_id": cards[0]["id"]},
    )
    assert r.status_code == 400


def test_change_request_flow(client, editor, admin, a_setup):
    cr = client.post(
        "/change-requests",
        headers=editor,
        json={
            "action": "update",
            "item_id": a_setup,
            "payload": {"description": "Updated via change request"},
            "description": "Tweak description",
            "reason": "Testing the workflow",
        },
    )
    assert cr.status_code == 201, cr.text
    cr_id = cr.json()["id"]
    assert cr.json()["status"] == "pending"

    # editor cannot approve
    assert client.post(f"/change-requests/{cr_id}/approve", headers=editor).status_code == 403

    ap = client.post(f"/change-requests/{cr_id}/approve", headers=admin, json={"note": "ok"})
    assert ap.status_code == 200
    assert ap.json()["status"] == "approved"

    updated = client.get(f"/items/{a_setup}", headers=admin).json()
    assert updated["description"] == "Updated via change request"


def test_graph_shape(client, admin):
    g = client.get("/graph", headers=admin).json()
    assert len(g["nodes"]) > len(g["edges"]) >= 1


def test_audit_records_history(client, admin, a_setup):
    audit = client.get(f"/audit?item_id={a_setup}", headers=admin).json()
    actions = {a["action"] for a in audit}
    assert {"create", "move", "state_change"} & actions


def test_export_import_roundtrip(client, admin):
    exp = client.get("/data/export?type=card", headers=admin)
    assert exp.status_code == 200
    assert exp.headers["content-type"].startswith("application/vnd.openxml")
    assert len(exp.content) > 500

    template = client.get("/data/template", headers=admin)
    assert template.status_code == 200


def test_manager_only_user_management(client, editor):
    assert client.get("/users", headers=editor).status_code == 200  # viewer+ can read
    r = client.post(
        "/users",
        headers=editor,
        json={"email": "x@lattice.io", "full_name": "X", "password": "secret1", "role": "viewer"},
    )
    assert r.status_code == 403  # editors cannot create users


# ─────────────────────── §2 admin-managed catalogs ───────────────────────
def test_catalog_seeded_and_enforced(client, admin):
    projects = client.get("/catalog?category=project", headers=admin).json()
    values = {p["value"] for p in projects}
    assert {"Falcon", "Sparrow", "Horizon"} <= values

    # creating an item with an unknown project is rejected
    bad = client.post(
        "/items",
        headers=admin,
        json={"type": "setup", "name": "Bad Proj Setup", "project": "TotallyUnknownProj"},
    )
    assert bad.status_code == 400
    assert "not a known project" in bad.json()["detail"]

    # a known project works
    ok = client.post(
        "/items",
        headers=admin,
        json={"type": "setup", "name": "Good Proj Setup", "project": "Falcon"},
    )
    assert ok.status_code == 201, ok.text


def test_catalog_crud_and_usage_guard(client, admin, editor):
    # editor cannot manage the catalog
    assert client.post(
        "/catalog", headers=editor, json={"category": "project", "value": "Nope"}
    ).status_code == 403

    created = client.post(
        "/catalog", headers=admin, json={"category": "project", "value": "Meteor"}
    )
    assert created.status_code == 201, created.text
    opt_id = created.json()["id"]

    # can't duplicate
    assert client.post(
        "/catalog", headers=admin, json={"category": "project", "value": "Meteor"}
    ).status_code == 400

    # unused option can be deleted
    assert client.delete(f"/catalog/{opt_id}", headers=admin).status_code == 204

    # an in-use option cannot be deleted
    falcon = next(
        o for o in client.get("/catalog?category=project", headers=admin).json()
        if o["value"] == "Falcon"
    )
    assert falcon["usage_count"] >= 1
    assert client.delete(f"/catalog/{falcon['id']}", headers=admin).status_code == 400


# ─────────────────── §6/§8 bidirectional linking + setup-direct cards ───────────────────
def test_create_with_children_cascades_location(client, admin):
    # a standalone card and assembly to be adopted
    card = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "Adopt Card", "card_type": "company"},
    ).json()
    asm = client.post(
        "/items", headers=admin, json={"type": "assembly", "name": "Adopt Assembly"},
    ).json()

    # a setup that adopts BOTH an assembly and a card directly (§8), at location 3
    setup = client.post(
        "/items", headers=admin,
        json={
            "type": "setup", "name": "Adopting Setup", "location_id": 3,
            "child_ids": [card["id"], asm["id"]],
        },
    )
    assert setup.status_code == 201, setup.text
    sid = setup.json()["id"]

    child_ids = {c["id"] for c in client.get(f"/items/{sid}", headers=admin).json()["children"]}
    assert {card["id"], asm["id"]} <= child_ids

    # both children inherited the setup's location (§9 cascade on link)
    assert client.get(f"/items/{card['id']}", headers=admin).json()["location_id"] == 3
    assert client.get(f"/items/{asm['id']}", headers=admin).json()["location_id"] == 3


def test_nested_link_cascades_whole_subtree(client, admin):
    # card inside assembly; then assembly moved into a setup at a new location
    card = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "Deep Card", "card_type": "company"},
    ).json()
    asm = client.post(
        "/items", headers=admin, json={"type": "assembly", "name": "Deep Assembly"},
    ).json()
    client.post(f"/items/{card['id']}/link", headers=admin, json={"parent_id": asm["id"]})

    setup = client.post(
        "/items", headers=admin,
        json={"type": "setup", "name": "Deep Setup", "location_id": 4},
    ).json()
    client.post(f"/items/{asm['id']}/link", headers=admin, json={"parent_id": setup["id"]})

    # the nested card followed all the way down to the setup's location
    assert client.get(f"/items/{card['id']}", headers=admin).json()["location_id"] == 4


# ─────────────────────── §2/§12 unique-serial integrity ───────────────────────
def test_unique_card_serial_must_be_unique(client, admin):
    first = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "FPGA", "card_type": "unique", "serial": "SN-UNIQ-1"},
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "FPGA", "card_type": "unique", "serial": "SN-UNIQ-1"},
    )
    assert dup.status_code == 400
    assert "already used" in dup.json()["detail"]


# ─────────────────────── §5 templates ───────────────────────
def test_templates_separated_from_live_items(client, admin):
    live = client.get("/items", headers=admin).json()
    assert all(not i["is_template"] for i in live)

    templates = client.get("/items?templates=true", headers=admin).json()
    assert len(templates) >= 2
    assert all(t["is_template"] for t in templates)

    # templates are absent from the hierarchy graph
    node_ids = {n["id"] for n in client.get("/graph", headers=admin).json()["nodes"]}
    assert not ({t["id"] for t in templates} & node_ids)


# ─────────────────────── §5 bulk operations ───────────────────────
def test_bulk_move_is_atomic(client, admin):
    ids = [
        client.post(
            "/items", headers=admin,
            json={"type": "card", "name": f"Bulk Card {n}", "card_type": "company"},
        ).json()["id"]
        for n in range(3)
    ]
    r = client.post(
        "/items/bulk",
        headers=admin,
        json={"action": "move", "item_ids": ids, "location_id": 5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["processed"] == 3
    for iid in ids:
        assert client.get(f"/items/{iid}", headers=admin).json()["location_id"] == 5


def test_bulk_rejects_missing_state(client, admin):
    card = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "Bulk State Card", "card_type": "company"},
    ).json()
    r = client.post(
        "/items/bulk",
        headers=admin,
        json={"action": "state_change", "item_ids": [card["id"]]},
    )
    assert r.status_code == 400


# ─────────────────────── §7 global search ───────────────────────
def test_global_search_ranks_and_scopes(client, admin, viewer):
    res = client.get("/search?q=Power", headers=admin).json()
    assert res["total"] >= 1
    assert any(h["kind"] == "item" for h in res["items"])

    # managers can find users; viewers cannot
    mgr_users = client.get("/search?q=Noa", headers=admin).json()["users"]
    assert any(u["title"].startswith("Noa") for u in mgr_users)
    assert client.get("/search?q=Noa", headers=viewer).json()["users"] == []


# ─────────────────────── editable map background ───────────────────────
def test_map_buildings_crud_and_permissions(client, admin, editor, viewer):
    # seeded default floor-plan buildings are readable by everyone
    seeded = client.get("/map/buildings", headers=viewer).json()
    assert len(seeded) >= 6
    assert {"Lab A", "Assembly Hall"} <= {b["name"] for b in seeded}

    # viewers cannot edit the map
    assert client.post("/map/buildings", headers=viewer, json={"name": "X"}).status_code == 403

    # editors can add and reshape a building
    created = client.post(
        "/map/buildings",
        headers=editor,
        json={"name": "New Wing", "x": 10, "y": 10, "width": 20, "height": 15, "color": "#ff0000"},
    )
    assert created.status_code == 201, created.text
    bid = created.json()["id"]

    moved = client.patch(f"/map/buildings/{bid}", headers=editor, json={"x": 35, "width": 26})
    assert moved.status_code == 200
    assert moved.json()["x"] == 35 and moved.json()["width"] == 26

    # only managers may delete
    assert client.delete(f"/map/buildings/{bid}", headers=editor).status_code == 403
    assert client.delete(f"/map/buildings/{bid}", headers=admin).status_code == 204
