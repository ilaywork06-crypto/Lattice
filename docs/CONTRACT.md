# Lattice — API & Event Contract

This is the shared contract between the **core-api**, the **notification-service**
and the **frontend**. All three must agree on it.

Base URLs (dev, host-exposed):
- Core API: `http://localhost:8000`
- Notification API: `http://localhost:8001`

## Auth
OAuth2 password flow, JWT bearer tokens. Both services validate the **same** JWT
(shared `JWT_SECRET`, `HS256`). The token `sub` claim is the numeric user id;
`role` claim is one of `viewer|editor|manager`.

- `POST /auth/login` — form-encoded `username` (=email) + `password`.
  → `{ access_token, token_type, role, full_name, user_id }`
- `GET /auth/me` (Bearer) → current `User`.
- `GET /auth/login-hints` — **unauthenticated**, feeds the sign-in screen's
  account shortcuts → `[{ full_name, email, role, password }]`.
  Returns only *active* accounts a manager marked `login_hint_visible`, and
  `password` only where a manager explicitly published one (`null` otherwise —
  the shortcut then fills the email alone). Nothing is exposed by default: new
  accounts start hidden, and the demo seed is what publishes the demo logins.

Send `Authorization: Bearer <token>` on every other request.

### Roles (increasing power)
- `viewer` — read only.
- `editor` — read + submit change-requests + import + create locations/thresholds.
- `manager` — everything + direct mutations + approvals + user management.

**Important workflow rule (§9):** direct item mutations (`POST/PATCH/DELETE
/items`, `/items/{id}/move|link|unlink|state`) require **manager**. Editors do
not mutate directly — they call `POST /change-requests`. The frontend must
branch on role: managers act directly; editors open a change-request dialog.

## Enums
- `ItemType`: `setup | assembly | card`
- `CardType`: `commercial | company | unique`
- `CardTracking`: `quantity | serial` — derived from `CardType` (`commercial` → `quantity`, the rest → `serial`), never sent by the client
- `ItemState`: `production | built | used | working | faulty`
- `StorageStatus`: `assembled | in_use | desiccator`
- `UserRole`: `viewer | editor | manager`
- `ChangeStatus`: `pending | approved | rejected`
- `ChangeAction`: `create | update | delete | move | link | unlink | state_change`

## Core API endpoints

### Items
- `GET /items` → `ItemListOut[]`. Query: `type,state,card_type,storage_status,project,industry,location_id,unassigned(bool),templates(bool),search,limit,offset`.
  `templates=true` returns only templates; default (`false`) excludes them (they never mix with live items).
  `ItemListOut = { id, type, name, industry, project, team, state, card_type, version, serial, quantity, storage_status, parent_id, location_id, location_name, children_count, is_template, manager_names[], updated_at }`
- `GET /items/{id}` → `ItemOut` (full: `is_template`, `location`, `parent` (brief), `children` (brief[]), `managers` (brief[]), `state_history[]`, `documents[]`, `extra_items[]`).
- `POST /items` (manager) body `ItemCreate` → `ItemOut`.
- `PATCH /items/{id}` (manager) body `ItemUpdate` → `ItemOut`.
- `DELETE /items/{id}` (manager) → 204.
- `POST /items/bulk` (manager) `{ action: move|state_change|delete|link|unlink, item_ids[req], location_id?, parent_id?, state?, note? }` → `{ processed, failed, errors[] }`. **Atomic**: the whole batch commits or rolls back together.
- `POST /items/{id}/move` (manager) `{ location_id, note? }` → `ItemOut` (cascades to descendants).
- `POST /items/{id}/link` (manager) `{ parent_id }` → `ItemOut` (cascades the parent's location through the whole adopted subtree).
- `POST /items/{id}/unlink` (manager) → `ItemOut`.
- `POST /items/{id}/state` (manager) `{ state, note? }` → `ItemOut`. Note is **required** when moving into/out of `faulty` (else 400).
- `POST /items/{id}/documents` (manager) `{ name, url?, doc_type? }` → `DocumentOut`.
- `DELETE /items/{id}/documents/{doc_id}` (manager) → 204.
- `POST /items/{id}/extras` (manager, setups only) `{ name, company_part_number?, serial?, signed_by? }` → `ExtraItemOut`.
- `DELETE /items/{id}/extras/{extra_id}` (manager) → 204.

`ItemCreate` fields: `type(req), name(req), industry, project, team, state(=production), description, dmz, location_id, parent_id, is_template(=false), card_type, responsible, lead, production_date(YYYY-MM-DD), version, serial, quantity(=1), storage_status, manager_ids[], child_ids[]`.
`ItemUpdate`: same mutable subset (all optional), plus `manager_ids`.
- `project`/`industry` must reference an **active catalog value** (§2) or the request 400s.
- `child_ids[]` (create only): existing items adopted as children — a setup accepts assemblies **and** cards (§8), an assembly accepts cards; each adopted subtree inherits the new parent's location (§9).
- `is_template=true` creates a reusable blueprint that stays out of the hierarchy, inventory, graph and export.
- **Names are unique** (trimmed, case-insensitive) across live setups, assemblies and quantity-tracked cards (else 400). Serial-tracked cards are exempt — a batch is many rows of one model, told apart by serial. Templates never take part.
- **Two kinds of card**, decided by `card_type` (required on every card):
  | `card_type` | tracking | `quantity` | `serial` |
  |---|---|---|---|
  | `commercial` | `quantity` | the stock on this row (≥1) | must be empty |
  | `company`, `unique` | `serial` | pinned to 1 | **required**, globally unique |
  Sending the field that doesn't apply 400s. Changing `card_type` normalises the leftover (a stranded serial is cleared, a quantity reset to 1) and records it in the audit log, since a PATCH cannot clear a field with `null`.
- A `serial` is globally unique across every card type and item (else 400).

### Change requests (§9)
- `POST /change-requests` (editor+) body `{ action, item_id?, item_type?, payload{}, description(req), reason(req) }` → `ChangeRequestOut`. Fires manager notification.
  - payload by action: `create`→ItemCreate dict; `update`→ItemUpdate dict; `move`→`{location_id, note?}`; `state_change`→`{state, note?}`; `link`→`{parent_id}`; `unlink`/`delete`→`{}`.
- `GET /change-requests?status=&mine=` → `ChangeRequestOut[]`.
- `GET /change-requests/{id}` → `ChangeRequestOut`.
- `POST /change-requests/{id}/approve` (manager) `{ note? }` → applies + notifies proposer.
- `POST /change-requests/{id}/reject` (manager) `{ note? }`.

`ChangeRequestOut = { id, action, item_id, item_type, item_name, payload, description, reason, status, proposed_by, reviewed_by, review_note, created_at, reviewed_at, proposer{brief}, reviewer{brief} }`.

### Inventory (§7, §12)
All stock figures are **sums of `Item.quantity`**, never row counts: a serial-tracked card pins that column to 1, a commercial card holds its whole stock on one row.

- `GET /inventory/summary` → `{ setups, assemblies, cards, cards_in_use, cards_desiccator, faulty_items, pending_change_requests, low_stock_alerts }`. The three `cards*` figures count physical units.
- `GET /inventory/cards?card_type=` → `InventoryGroup[]`.
- `GET /inventory/desiccator?card_type=` → `InventoryGroup[]`.
  `InventoryGroup = { card_type, tracking, name, version, production_date, total, in_use, desiccator, assembled, records, serials[] }`.
  `tracking` (`quantity|serial`) and `records` (rows behind `total`) explain where the number came from; `serials[]` lists every unit of a serial-tracked group. Commercial cards are included — they used to be filtered out entirely.
  **One card name is several groups**: the key is `(card_type, name, version, production_date)`, so 8 boards under one name across two versions come back as `total: 6` + `total: 2` and *no* group says 8. The parts always sum to the whole; the UI adds the per-model subtotal on top.
- `GET /inventory/thresholds` → `ThresholdOut[]` (`{ id, card_type, tracking, name, version, min_quantity, editor_email, current_quantity, is_low }`).
- `GET /inventory/low-stock` → `ThresholdOut[]`.
- `POST /inventory/thresholds` (editor+) `ThresholdCreate` → `ThresholdOut`.
- `DELETE /inventory/thresholds/{id}` (manager) → 204.

### Catalog — admin vocabularies (§2)
- `GET /catalog?category=project|industry&active_only=` (viewer+) → `CatalogOptionOut[]` (`{ id, category, value, description, active, sort_order, usage_count }`).
- `POST /catalog` (manager) `{ category, value, description?, active?, sort_order? }` → `CatalogOptionOut`.
- `PATCH /catalog/{id}` (manager) `{ value?, description?, active?, sort_order? }` (renaming a value re-points existing items).
- `DELETE /catalog/{id}` (manager) → 204 (400 if the value is still in use — deactivate instead).

### Search — global (§7)
- `GET /search?q=&limit=` (viewer+) → `{ query, total, items[], locations[], users[] }`.
  `SearchHit = { kind: item|location|user, id, title, subtitle, badge, state?, link }`. Ranked exact → prefix → word → substring. `users[]` is populated for **managers only**.

### Locations (floor-plan map)
- `GET /locations` → `LocationOut[]` (`{ id, name, building, room, x, y, notes, item_count }`; x,y are 0..100 floor-plan coords).
- `POST /locations` (editor+), `PATCH /locations/{id}` (editor+), `DELETE /locations/{id}` (manager).

### Map buildings (editable floor-plan background)
- `GET /map/buildings` (viewer+) → `MapBuildingOut[]` (`{ id, name, x, y, width, height, color, notes, sort_order }`;
  x,y are the top-left corner, all four 0..100 so the plan is resolution-independent). Ordered by `sort_order, id`.
- `POST /map/buildings` (editor+), `PATCH /map/buildings/{id}` (editor+), `DELETE /map/buildings/{id}` (manager).
  `width`/`height` must be `> 0`.

### Graph
- `GET /graph?root_id=` → `{ nodes:[{id,label,type,state,card_type}], edges:[{source,target}] }` (source=parent, target=child). Templates are excluded.

### Audit (§10)
- `GET /audit?item_id=&limit=` → `AuditOut[]` (`{ id, item_id, item_name, action, summary, details, user_id, user_name, created_at }`).
- `GET /audit/my-items?period=day|week|month` (manager) → changes on items linked to the current manager in the period.

### Users (§8)
- `GET /users` (viewer+) → `UserOut[]`, `GET /users/managers` (viewer+) → `UserBrief[]`.
  `UserOut = { id, full_name, email, role, is_active, created_at, login_hint_visible, has_login_hint_password }` — the hint password itself is never returned here, only whether one is published.
- `POST /users` (manager) `{ email, full_name, password, role }`.
- `PATCH /users/{id}` (manager) `{ full_name?, role?, is_active?, password?, login_hint_visible?, login_hint_password? }`.
  `login_hint_password: ""` withdraws a published password (leaving an email-only shortcut); omitting the field leaves it untouched. Both hint fields land in the audit log.
- `DELETE /users/{id}` (manager).

### Import / Export (§11)
- `GET /data/template?type=` → xlsx (download).
- `GET /data/export?type=` → xlsx (download).
- `POST /data/import` (editor+) multipart `file` (.xlsx) → `{ created, errors:[{row,error}] }`.

## Notification API (notification-service, port 8001)
Validates the same Bearer JWT; derives the current user from `sub`.
- `GET /notifications?unread_only=&limit=` → `Notification[]` (newest first) for the current user.
  `Notification = { id, type, title, body, payload, link, read, created_at }`.
  `payload` is the source event's structured context (`null` for older rows). A `inventory.low_stock` alert carries `{ components: [{ threshold_id, name, card_type, tracking, version, current_quantity, min_quantity, shortfall }] }`, which the UI renders as a list — `body` holds the same list as plain text for email.
- `GET /notifications/unread-count` → `{ count }`.
- `POST /notifications/{id}/read` → 204.
- `POST /notifications/read-all` → 204.
- `GET /health`.

## Event bus (Redis pub/sub, channel `lattice:events`)
core-api publishes `Event` JSON; notification-service consumes and fans out to
in-app notifications (one row per recipient with a `user_id`) + emails (SMTP for
recipients with an `email`).

```
Event = {
  id, type, created_at, title, body, link,
  recipients: [{ user_id?, email?, role? }],
  payload: {}
}
```
`EventType`: `change_request.submitted | change_request.approved |
change_request.rejected | inventory.low_stock | item.state_changed`.

`inventory.low_stock` is published as **one digest per recipient**, listing only
the groups that recipient is responsible for (`recipients` therefore holds a
single entry), with the components in `payload.components[]`.

The `lattice_shared` package (already built) provides `EventBus` and `Event`:
`from lattice_shared.events import EventBus, Event, EventType, Recipient`.
`EventBus(redis_url).subscribe()` is an async generator yielding `Event`s.

## Demo logins (seeded)
- `admin@lattice.io` / `admin1234` — manager (bootstrap)
- `noa@lattice.io` / `password` — manager (linked to the demo setup)
- `dana@lattice.io` / `password` — editor
- `amir@lattice.io` / `password` — viewer
