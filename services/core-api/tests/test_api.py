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
    assert s["setups"] >= 1 and s["assemblies"] >= 1
    assert s["cards"] >= s["cards_desiccator"] >= 1
    # The tile counts physical units, so it must equal the inventory table it
    # summarises — a dashboard that disagrees with /inventory is exactly the
    # "where does this number come from?" problem.
    groups = client.get("/inventory/cards", headers=admin).json()
    assert s["cards"] == sum(g["total"] for g in groups)


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


def test_edit_form_can_change_location_and_it_cascades(client, admin):
    """The edit dialog sends `location_id` in its PATCH body alongside the other
    fields. It used to be dropped silently (absent from ItemUpdate), so the save
    reported success while the item never moved."""
    assembly = client.get("/items?type=assembly", headers=admin).json()[0]
    aid = assembly["id"]
    before = client.get(f"/items/{aid}", headers=admin).json()
    assert before["children"], "need an assembly with cards to prove the cascade"
    target = 3 if before["location_id"] != 3 else 2

    r = client.patch(
        f"/items/{aid}",
        headers=admin,
        json={"name": before["name"], "location_id": target},
    )
    assert r.status_code == 200, r.text
    assert r.json()["location_id"] == target

    after = client.get(f"/items/{aid}", headers=admin).json()
    assert after["location_id"] == target
    # a container drags its contents (§3) — the plain field write would not have
    for child in after["children"]:
        assert child["location_id"] == target, "cards left behind at the old location"

    # and the move is auditable, not silent
    actions = [a["action"] for a in client.get(f"/audit?item_id={aid}", headers=admin).json()]
    assert "move" in actions


def test_edit_form_can_change_state_and_keeps_the_faulty_note_rule(client, admin, a_setup):
    """`state` was dropped by ItemUpdate just like `location_id` was. Routing it
    through change_state means it still records history and still demands a note
    for faulty transitions instead of quietly writing the column."""
    before = client.get(f"/items/{a_setup}", headers=admin).json()
    history_before = len(before["state_history"])

    # a plain transition sticks
    r = client.patch(f"/items/{a_setup}", headers=admin, json={"state": "working"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "working"

    # going faulty without an explanation is refused — with a 400, not a 500
    bad = client.patch(f"/items/{a_setup}", headers=admin, json={"state": "faulty"})
    assert bad.status_code == 400, bad.text
    assert "note" in bad.json()["detail"].lower()
    assert client.get(f"/items/{a_setup}", headers=admin).json()["state"] == "working"

    # with the note it goes through and lands in the history
    ok = client.patch(
        f"/items/{a_setup}",
        headers=admin,
        json={"state": "faulty", "state_note": "capacitor burned out"},
    )
    assert ok.status_code == 200, ok.text
    after = client.get(f"/items/{a_setup}", headers=admin).json()
    assert after["state"] == "faulty"
    assert len(after["state_history"]) > history_before
    assert any("capacitor" in (h["note"] or "") for h in after["state_history"])


def test_domain_errors_are_400_on_every_route_not_just_create(client, admin):
    """PATCH /items had no `except DomainError`, so a rule violation surfaced as
    a bare 500 with no explanation. A global handler covers every route."""
    item = client.get("/items?type=assembly", headers=admin).json()[0]
    r = client.patch(
        f"/items/{item['id']}", headers=admin, json={"project": "NOT-A-REAL-PROJECT"}
    )
    assert r.status_code == 400, f"expected a clean 400, got {r.status_code}"
    assert "not a known project" in r.json()["detail"]


def test_paging_bounds_reject_negatives_instead_of_500(client, admin):
    """Postgres rejects a negative LIMIT/OFFSET at the driver level, so an
    unbounded Query() turned `?offset=-1` into an unhandled 500."""
    for url in ("/items?offset=-1", "/items?limit=-5", "/audit?limit=-5", "/search?q=a&limit=0"):
        assert client.get(url, headers=admin).status_code == 422, url


def test_malformed_proposal_is_rejected_not_a_500(client, editor, admin, a_setup):
    """`payload` is a free-form blob chosen by the proposer, so approval has to
    survive it being nonsense — with a readable 400, not an unhandled 500."""
    for action, payload in (("create", {}), ("move", {}), ("state_change", {})):
        cr = client.post(
            "/change-requests",
            headers=editor,
            json={
                "action": action,
                "item_id": a_setup,
                "payload": payload,
                "description": "malformed",
                "reason": "testing",
            },
        ).json()
        r = client.post(f"/change-requests/{cr['id']}/approve", headers=admin)
        assert r.status_code == 400, f"{action}: got {r.status_code}"
        assert "not valid" in r.json()["detail"]
        # the proposal must survive so a manager can still reject it
        still = client.get(f"/change-requests/{cr['id']}", headers=admin).json()
        assert still["status"] == "pending"


def test_desiccator_endpoint_only_returns_desiccator_stock(client, admin):
    """The filter was `desiccator > 0 or total > 0`; a group only exists when it
    has a card, so `total > 0` always held and this mirrored /inventory/cards —
    leaving the UI's All/Desiccator toggle with nothing to do."""
    # a card that is in use and therefore holds nothing in the desiccator
    client.post(
        "/items",
        headers=admin,
        json={
            "type": "card",
            "name": "Bench-Only Card",
            "card_type": "company",
            "serial": "BENCH-001",
            "storage_status": "in_use",
        },
    )
    everything = client.get("/inventory/cards", headers=admin).json()
    only_desiccator = client.get("/inventory/desiccator", headers=admin).json()

    names = {g["name"] for g in everything}
    desiccator_names = {g["name"] for g in only_desiccator}
    assert "Bench-Only Card" in names
    assert "Bench-Only Card" not in desiccator_names
    assert all(g["desiccator"] > 0 for g in only_desiccator)


def test_password_over_the_bcrypt_byte_limit_is_a_clean_422(client, admin):
    """bcrypt raises above 72 *bytes*; unguarded that was a 500. Hebrew is two
    bytes a character, so this is reachable well under 72 characters."""
    for password in ("x" * 100, "סיסמה" * 10):
        r = client.post(
            "/users",
            headers=admin,
            json={
                "email": f"long{len(password)}@lattice.io",
                "full_name": "Long",
                "password": password,
                "role": "viewer",
            },
        )
        assert r.status_code == 422, f"{len(password.encode())} bytes -> {r.status_code}"


def test_search_treats_like_wildcards_literally(client, admin):
    """`%` is a LIKE wildcard: unescaped it matched every row in the database."""
    assert client.get("/search?q=%25", headers=admin).json()["total"] == 0
    assert client.get("/items?search=%25", headers=admin).json() == []


def test_deleting_a_user_with_proposals_is_refused_not_crashed(client, admin, editor):
    """change_requests.proposed_by is a non-nullable FK with no ON DELETE rule,
    so removing a proposer raised an IntegrityError and surfaced as a 500."""
    everyone = client.get("/users", headers=admin).json()
    dana = next(u for u in everyone if u["email"] == "dana@lattice.io")
    r = client.delete(f"/users/{dana['id']}", headers=admin)
    assert r.status_code == 409, r.status_code
    assert "deactivate" in r.json()["detail"].lower()
    # and the account is still there, intact
    assert any(u["id"] == dana["id"] for u in client.get("/users", headers=admin).json())


def test_a_no_op_save_writes_no_audit_entry(client, admin, a_setup):
    """The edit form always posts `manager_ids`, and update_item assigned it
    unconditionally — so re-saving an unchanged item logged a bogus
    "(manager_ids)" change every time, with `None` as the old value."""
    before = client.get(f"/items/{a_setup}", headers=admin).json()
    count_before = len(client.get(f"/audit?item_id={a_setup}", headers=admin).json())

    payload = {
        "name": before["name"],
        "manager_ids": [m["id"] for m in before["managers"]],
    }
    for _ in range(3):
        assert client.patch(f"/items/{a_setup}", headers=admin, json=payload).status_code == 200

    after = client.get(f"/audit?item_id={a_setup}", headers=admin).json()
    assert len(after) == count_before, "a save that changes nothing must not be logged"

    # a real change is still recorded, and with the true previous value
    managers = client.get("/users/managers", headers=admin).json()
    changed = client.patch(
        f"/items/{a_setup}", headers=admin, json={"manager_ids": [managers[0]["id"]]}
    )
    assert changed.status_code == 200
    entries = client.get(f"/audit?item_id={a_setup}", headers=admin).json()
    assert len(entries) == count_before + 1
    old, new = entries[0]["details"]["changed"]["manager_ids"]
    assert old == payload["manager_ids"] and new == [managers[0]["id"]]


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
        json={
            "type": "card", "name": "Adopt Card",
            "card_type": "company", "serial": "ADOPT-001",
        },
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
        json={
            "type": "card", "name": "Deep Card",
            "card_type": "company", "serial": "DEEP-001",
        },
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
            json={
                "type": "card", "name": f"Bulk Card {n}",
                "card_type": "company", "serial": f"BULK-{n:03d}",
            },
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
        json={
            "type": "card", "name": "Bulk State Card",
            "card_type": "company", "serial": "BULK-STATE-001",
        },
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


# ─────────────── §12 a commercial card is a quantity, not N rows ───────────────
def test_commercial_card_carries_its_quantity_on_one_row(client, admin):
    created = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "COTS RS-422 Adapter", "card_type": "commercial",
            "quantity": 25, "storage_status": "desiccator",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["quantity"] == 25

    group = next(
        g for g in client.get("/inventory/cards", headers=admin).json()
        if g["name"] == "COTS RS-422 Adapter"
    )
    # 25 units held on a single record — and the group says exactly that, which
    # is the point: the number is explainable without counting rows by hand.
    assert (group["total"], group["records"], group["desiccator"]) == (25, 1, 25)
    assert group["tracking"] == "quantity"


def test_a_model_is_split_by_version_and_the_parts_sum_to_the_whole(client, admin):
    """One card *name* is many inventory rows — one per version/production batch.
    So 5 boards under one name read as 3 + 2, and no single row ever says 5;
    the parts adding up to the whole is the contract the UI's per-model subtotal
    relies on. Reading a part as if it were the total is exactly the confusion
    this endpoint has to make impossible."""
    for version, count in (("1.0", 3), ("2.0", 2)):
        for i in range(count):
            r = client.post(
                "/items", headers=admin,
                json={
                    "type": "card", "name": "Sum Check Board", "card_type": "company",
                    "version": version, "serial": f"SUM-{version}-{i}",
                },
            )
            assert r.status_code == 201, r.text

    rows = client.get("/items?type=card&search=Sum Check Board", headers=admin).json()
    groups = [
        g for g in client.get("/inventory/cards", headers=admin).json()
        if g["name"] == "Sum Check Board"
    ]
    assert sorted(g["total"] for g in groups) == [2, 3]
    assert sum(g["total"] for g in groups) == len(rows) == 5


def test_commercial_cards_are_no_longer_missing_from_inventory(client, admin):
    """They were filtered out of every group, so their stock was simply absent."""
    names = {g["name"] for g in client.get("/inventory/cards", headers=admin).json()}
    assert "COTS Ethernet NIC" in names


def test_summary_counts_units_not_rows(client, admin):
    before = client.get("/inventory/summary", headers=admin).json()["cards"]
    client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "COTS Resistor Pack", "card_type": "commercial",
            "quantity": 50, "storage_status": "desiccator",
        },
    )
    after = client.get("/inventory/summary", headers=admin).json()["cards"]
    assert after == before + 50, "one row, fifty physical cards"


def test_a_commercial_card_cannot_carry_a_serial(client, admin):
    r = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "COTS With Serial",
            "card_type": "commercial", "serial": "COTS-1",
        },
    )
    assert r.status_code == 400
    assert "quantity" in r.json()["detail"]


def test_a_serialised_card_needs_a_serial_and_refuses_a_quantity(client, admin):
    missing = client.post(
        "/items", headers=admin,
        json={"type": "card", "name": "Serial-less Board", "card_type": "unique"},
    )
    assert missing.status_code == 400
    assert "must have a serial" in missing.json()["detail"]

    batched = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "Batched Board", "card_type": "company",
            "serial": "BATCH-1", "quantity": 10,
        },
    )
    assert batched.status_code == 400
    assert "per unit" in batched.json()["detail"]


def test_a_card_without_a_card_type_is_refused(client, admin):
    """Without one there is no answer to "is this counted by quantity or serial?"."""
    r = client.post("/items", headers=admin, json={"type": "card", "name": "Untyped Card"})
    assert r.status_code == 400
    assert "card type" in r.json()["detail"]


def test_switching_a_card_to_commercial_clears_its_stranded_serial(client, admin):
    card = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "Reclassified Board",
            "card_type": "company", "serial": "RECLASS-1",
        },
    ).json()
    # A PATCH cannot clear a field by sending null, so the type switch has to.
    r = client.patch(
        f"/items/{card['id']}", headers=admin,
        json={"card_type": "commercial", "quantity": 7},
    )
    assert r.status_code == 200, r.text
    assert r.json()["serial"] is None and r.json()["quantity"] == 7
    # ...and the serial's disappearance is on the record, not silent (§10)
    entries = client.get(f"/audit?item_id={card['id']}", headers=admin).json()
    assert any("serial" in (e["details"].get("changed") or {}) for e in entries)


def test_a_serial_is_unique_across_every_card_type(client, admin):
    first = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "Serial Guard A",
            "card_type": "company", "serial": "GUARD-1",
        },
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "Serial Guard B",
            "card_type": "unique", "serial": "GUARD-1",
        },
    )
    assert dup.status_code == 400
    assert "already used" in dup.json()["detail"]


# ─────────────────────── unique names ───────────────────────
def test_two_items_cannot_share_a_name(client, admin):
    assert client.post(
        "/items", headers=admin, json={"type": "assembly", "name": "Unique Name Module"}
    ).status_code == 201

    # same name, and the same name modulo case and padding, across types
    for name in ("Unique Name Module", "  unique name module  "):
        dup = client.post("/items", headers=admin, json={"type": "setup", "name": name})
        assert dup.status_code == 400, name
        assert "already used" in dup.json()["detail"]

    # renaming an existing item onto a taken name is refused just the same
    other = client.post(
        "/items", headers=admin, json={"type": "assembly", "name": "Some Other Module"}
    ).json()
    assert client.patch(
        f"/items/{other['id']}", headers=admin, json={"name": "Unique Name Module"}
    ).status_code == 400


def test_serialised_cards_may_share_a_name_but_quantity_cards_may_not(client, admin):
    """A batch is many rows of one model; the serial is what tells them apart."""
    for i in range(2):
        r = client.post(
            "/items", headers=admin,
            json={
                "type": "card", "name": "Batch Board", "card_type": "company",
                "serial": f"BATCH-BOARD-{i}",
            },
        )
        assert r.status_code == 201, r.text

    # a quantity-tracked card, by contrast, is one row per real thing
    assert client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "Single COTS Board",
            "card_type": "commercial", "quantity": 3,
        },
    ).status_code == 201
    dup = client.post(
        "/items", headers=admin,
        json={
            "type": "card", "name": "single cots board",
            "card_type": "commercial", "quantity": 1,
        },
    )
    assert dup.status_code == 400


def test_duplicate_location_names_are_refused(client, admin):
    assert client.post(
        "/locations", headers=admin, json={"name": "Overflow Shelf"}
    ).status_code == 201
    dup = client.post("/locations", headers=admin, json={"name": " overflow shelf "})
    assert dup.status_code == 400
    assert "already exists" in dup.json()["detail"]


# ─────────────────── §8 sign-in shortcuts (login page) ───────────────────
def _user_id(client, admin, email: str) -> int:
    return next(u["id"] for u in client.get("/users", headers=admin).json() if u["email"] == email)


def test_login_hints_expose_only_what_a_manager_published(client, admin):
    """The endpoint is unauthenticated by necessity — it feeds the login page —
    so what it returns is exactly what a manager chose to publish, no more."""
    public = client.get("/auth/login-hints")  # deliberately no token
    assert public.status_code == 200
    hints = {h["email"]: h for h in public.json()}
    assert "dana@lattice.io" in hints, "the demo seed publishes the demo accounts"
    assert hints["dana@lattice.io"]["password"] == "password"
    assert set(hints["dana@lattice.io"]) == {"full_name", "email", "role", "password"}

    dana_id = _user_id(client, admin, "dana@lattice.io")

    # hidden → gone from the login page entirely
    hidden = client.patch(f"/users/{dana_id}", headers=admin, json={"login_hint_visible": False})
    assert hidden.status_code == 200
    assert hidden.json()["login_hint_visible"] is False
    assert "dana@lattice.io" not in {h["email"] for h in client.get("/auth/login-hints").json()}

    # visible again but with the password withdrawn ("" clears it): the shortcut
    # fills the email and the password still has to be typed
    shown = client.patch(
        f"/users/{dana_id}",
        headers=admin,
        json={"login_hint_visible": True, "login_hint_password": ""},
    )
    assert shown.json()["has_login_hint_password"] is False
    published = client.get("/auth/login-hints").json()
    assert next(h for h in published if h["email"] == "dana@lattice.io")["password"] is None

    # ...and signing in with that account still works, so hiding the hint never
    # touches the credentials themselves
    assert client.post(
        "/auth/login", data={"username": "dana@lattice.io", "password": "password"}
    ).status_code == 200

    # restore the demo state for the rest of the suite
    client.patch(
        f"/users/{dana_id}",
        headers=admin,
        json={"login_hint_visible": True, "login_hint_password": "password"},
    )


def test_a_deactivated_account_drops_off_the_login_page(client, admin):
    created = client.post(
        "/users", headers=admin,
        json={
            "email": "kiosk@lattice.io", "full_name": "Kiosk Demo",
            "password": "kiosk1234", "role": "viewer",
        },
    ).json()
    assert created["login_hint_visible"] is False, "new accounts are never published"

    client.patch(
        f"/users/{created['id']}", headers=admin,
        json={"login_hint_visible": True, "login_hint_password": "kiosk1234"},
    )
    assert "kiosk@lattice.io" in {h["email"] for h in client.get("/auth/login-hints").json()}

    client.patch(f"/users/{created['id']}", headers=admin, json={"is_active": False})
    assert "kiosk@lattice.io" not in {h["email"] for h in client.get("/auth/login-hints").json()}


def test_only_managers_may_publish_a_sign_in_shortcut(client, editor, admin):
    amir_id = _user_id(client, admin, "amir@lattice.io")
    r = client.patch(f"/users/{amir_id}", headers=editor, json={"login_hint_visible": False})
    assert r.status_code == 403


def test_publishing_a_shortcut_is_audited(client, admin):
    amir_id = _user_id(client, admin, "amir@lattice.io")
    client.patch(f"/users/{amir_id}", headers=admin, json={"login_hint_visible": False})
    entry = next(
        a for a in client.get("/audit", headers=admin).json() if a["action"] == "user.update"
    )
    assert entry["details"]["login_hint_visible"] is False
    client.patch(f"/users/{amir_id}", headers=admin, json={"login_hint_visible": True})


# ─────────────────── §12 low-stock alerts list their components ───────────────────
def test_low_stock_alert_carries_the_component_list(client, admin, monkeypatch):
    """It used to be one prose sentence per threshold, so a manager watching
    several groups got several emails and had to read them to learn what was
    short. One digest per recipient now, with the components as data."""
    import asyncio

    from lattice_core import events as events_mod
    from lattice_core.database import SessionLocal
    from lattice_core.services import inventory as inv

    published = []

    async def capture(event):
        published.append(event)

    monkeypatch.setattr(events_mod, "publish_event", capture)

    with SessionLocal() as db:
        lows = asyncio.run(inv.check_and_alert_low_stock(db))

    assert lows, "the demo seed deliberately keeps groups under their minimum"
    assert published

    for event in published:
        assert len(event.recipients) == 1, "one digest per recipient, not per threshold"
        components = event.payload["components"]
        assert components
        for c in components:
            assert {
                "name", "card_type", "tracking", "version",
                "current_quantity", "min_quantity", "shortfall",
            } <= set(c)
            assert c["current_quantity"] <= c["min_quantity"]
            # the plain-text body lists them too, for the email
            assert c["name"] in event.body

    # a manager watching several short groups gets them in ONE notification
    assert max(len(e.payload["components"]) for e in published) >= 2


def test_default_floor_plan_backfills_into_an_already_seeded_db():
    """The demo seed only runs on a virgin DB, so the floor-plan must be able to
    land on a database that was created before the map existed."""
    from lattice_core.database import SessionLocal
    from lattice_core.models import MapBuilding
    from lattice_core.seed import _ensure_map_buildings

    with SessionLocal() as db:
        db.query(MapBuilding).delete()  # simulate a pre-map database
        db.commit()
        assert db.query(MapBuilding).count() == 0

        _ensure_map_buildings(db)
        db.commit()
        assert db.query(MapBuilding).count() == 6

        # ...and it must not duplicate them on the next boot
        _ensure_map_buildings(db)
        db.commit()
        assert db.query(MapBuilding).count() == 6
