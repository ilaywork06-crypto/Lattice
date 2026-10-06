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
  the shortcut then fills the email alone). Nothing is exposed by default.

Send `Authorization: Bearer <token>` on every other request.

### Roles (increasing power)
- `viewer` — read; may **propose a location change** (`move` change request) and nothing else.
- `editor` — read + propose any change (items *and* templates) + create locations/thresholds + stage uploads.
- `manager` — everything + direct mutations + approvals + templates + catalog/desiccator + import + users.

**Workflow rule (§9):** direct mutations of items and templates require
**manager**. Everyone else calls `POST /change-requests`; on approval the server
runs the very same service functions a manager would.

## Enums
- `ItemType`: `setup | assembly | card`
- `CardType`: `copied | house | white | factory | commercial` (formerly `unique` → `copied`, `company` → `house`)
- `CardTracking`: `quantity | serial` — derived from `CardType` (`commercial` → `quantity`, the rest → `serial`)
- `ItemState`: `built | ok | faulty | destroyed` — every new item is `built` unless its template's status field says otherwise
- `StorageStatus`: `desiccator | assembled | in_use` — **derived**, never stored (see Inventory): `desiccator` = at a desiccator location (loose *or* assembled), `assembled` = inside an item elsewhere, `in_use` = loose elsewhere
- `UserRole`: `viewer | editor | manager`
- `ChangeStatus`: `pending | approved | rejected`
- `ChangeAction`: `create | update | delete | move | link | unlink | state_change | template_create | template_update`
- `CatalogCategory`: `project | industry | team`
- `FieldMode`: `fixed | choice | item`
- `FieldType`: `text | description | string | serial_string | link | enum | letter | date | integer | decimal | boolean | files | industry | project | team | managers | responsible | location | parent | status | quantity`

## Templates — every item is made from one

A template is the blueprint of one *kind* of thing: one named card, one
assembly, one setup. It owns the name, the card type, the three-letter serial
prefix, the fields, and (for containers) which templates may sit inside it.
Items of one template share its name and are told apart by their serial.

### Fields
Each field has a `label`, a `field_type`, a `mode`, a `required` flag, a
`config` and (for fixed fields) a `fixed_value`.

| `mode` | UI colour | who sets the value |
|---|---|---|
| `fixed` | white | the template — one value shared by every item, read through the template, so editing it changes every item |
| `choice` | white with ▾ | the template defines `config.options`; each item picks one (the first is the default) |
| `item` | grey | filled in when an item is created |

`required` (★) means: a fixed field must have its value; a list must be
non-empty; a per-item field must be filled when an item is created.

Per-type rules:
- `description`: text with at least `config.min_length` (default 8) non-blank characters.
- `string` / `serial_string`: optional `config.pattern`, e.g. `"XX-#####"` — `#` is a digit the user types, every other character is filled in automatically. Both `"12345"` and `"XX-12345"` are accepted; the stored value is the full form.
- `enum`: `config.options` is the list of strings.
- `letter`: `A`–`Z`. `date`: `YYYY-MM-DD`. `link`: a URL with a scheme. `integer`, `decimal`, `boolean`, `quantity` (≥ 1).
- **System types** — `industry`, `project`, `team` (catalog ids), `managers` (manager user ids; links every item to those managers), `responsible` (any user id), `location`, `parent` (item id), `status`, `quantity` — are stored in real columns on the item; **at most one of each per template**.
- `location`, `parent`, `status`, `quantity` describe each unit, so they can be `item` or `choice` but never `fixed`. `parent` is never `choice`.
- `quantity` only on **commercial** card templates; setups have no `parent`.
- `files`: values are document ids (see Documents). A fixed files field holds files uploaded to the template.
- A field's `field_type` cannot change once it exists (remove it and add a new one).

### Endpoints
- `GET /templates?type=&card_type=&search=` (viewer+) → `TemplateSummary[]`
  `TemplateSummary = { id, type, name, card_type, serial_prefix, tracking, description, counts{built,ok,faulty,total,destroyed}, child_template_ids[], parent_template_ids[], field_count, updated_at }`
  `counts` are units per state (sums of `quantity`); `total` **excludes destroyed**.
- `GET /templates/{id}` → `TemplateOut` = summary + `fields: TemplateFieldOut[]`, `children: [{ template{brief}, min_count, max_count }]`, `child_templates[]`, `parent_templates[]`, `next_serial`, `created_at`.
  `TemplateFieldOut = { id, key, label, field_type, mode, required, position, config, fixed_value, fixed_display, options_display[], files[] }` (`*_display` are readable names for stored ids).
- `POST /templates` (manager) `TemplateCreate = { type, name, card_type?, serial_prefix, description?, fields: TemplateFieldIn[], children?: TemplateChildIn[], child_template_ids[], source_template_id? }` → `TemplateOut`.
  `TemplateFieldIn = { id?, key?, label, field_type, mode, required, config, fixed_value?, copy_files_from? }`.
  `TemplateChildIn = { template_id, min_count = 0, max_count = null }` — how many units of that template one item holds: at least `min_count` for the item to be *complete*, never more than `max_count` (`null` = no limit). `child_template_ids` is the older form without limits; it is ignored when `children` is sent, and on `PATCH` it keeps the limits of the ids it lists.
  **Duplicating** a template is a create prefilled from another: `source_template_id` is recorded in the audit, and `copy_files_from` on a fixed files field copies that field's files (each gets its own stored copy).
- `PATCH /templates/{id}` (manager) — any of the above except `type`. `fields`, when sent, is the **complete** list after the edit (`id` marks an existing field; missing ones are removed). Changes **propagate**: a fixed system value (e.g. managers) is rewritten on every item; switching a field from fixed to per-item copies the old value into each item.
- `DELETE /templates/{id}` (manager) → 204; 400 while any item was made from it.
- `POST /templates/{id}/fields/{field_id}/files` (manager) multipart `file` → `DocumentOut` (fixed files fields).
- `DELETE /templates/{id}/files/{doc_id}` (manager) → 204.

Rules: names are unique per type (case-insensitive); `serial_prefix` is three
Latin letters, unique per type; a card template needs a `card_type`, other
types must not have one; children: a setup may contain assembly and card
templates, an assembly card templates (each pair at most once); a template
can't be removed from a container's list while items of it sit inside items of
that container, and a maximum can't be lowered below what an item already holds.

### Field groups (catalog)
Named, reusable sets of field definitions. Loading one into the template editor
**copies** its fields; templates never stay linked to a group.
- `GET /field-groups?search=` (viewer+) → `FieldGroupOut[] = { id, name, description, fields: [{ key, label, field_type, mode, required, position, config, fixed_value, fixed_display, options_display[] }], created_at, updated_at }`. `search` matches the group name, description or a field's name.
- `GET /field-groups/{id}`, `POST /field-groups` `{ name, description?, fields: TemplateFieldIn[] }`, `PATCH /field-groups/{id}` (any of those; `fields` = the complete list), `DELETE /field-groups/{id}` — writes are manager-only. Names are unique (case-insensitive); fields are validated like a template's.

## Serials

`C-XXX-###` (card), `A-XXX-###` (assembly), `S-XXX-###` (setup). `XXX` is the
template's prefix; `###` is issued automatically as **one above the highest
number already used under that type + prefix** (grows past 999). A serial can
be set or edited by hand: it must keep the type letter and the template's
prefix (or the prefix the item was issued under) and is **unique system-wide**
(unique index; 400 with an explanation on a clash).

## Core API endpoints

### Items
- `GET /items` → `ItemListOut[]`. Query: `type, template_id, state, card_type, storage_status, location_id, parent_id, unassigned(bool), include_destroyed(bool=true), child_of_template, parent_of_template, search, limit(≤5000), offset`.
  `child_of_template=T`: items whose template may be placed inside template T; `parent_of_template=T`: items whose template may contain T.
  `ItemListOut = { id, type, template_id, name, serial, state, card_type, quantity, storage_status, parent_id, parent_label, location_id, location_name, industry, project, team, children_count, missing_children, manager_names[], updated_at }`
- `GET /items/{id}` → `ItemOut = { id, type, template{brief}, name, serial, state, card_type, tracking, quantity, storage_status, parent_id, location_id, location, parent{brief}, children[brief], industry, project, team ({id,value}), responsible, managers[], fields: ItemFieldOut[], state_history[], documents[], extra_items[], child_templates[], parent_templates[], composition[], is_complete, created_at, updated_at }`
  `composition` = one row per allowed child template: `{ template{brief}, min_count, max_count, count, missing, is_full }` (`count` in units, destroyed ones excluded); `is_complete` = nothing missing.
  `ItemFieldOut = { field_id, key, label, field_type, mode, required, config, value, display, missing }` — every field of the template, with the effective value (`fixed` ones from the template).
- `POST /items` (manager) `ItemCreate = { template_id(req), values{key: value}, serial?, child_ids[] }` → `ItemOut`.
  `values` holds the template's `item`/`choice` fields by key (a `choice` field left out gets its first value). Sending a `fixed` field, an unknown key, an invalid value or leaving a required field empty → 400 with `errors: [{field, label, error}]` listing **every** problem. A new card with no location goes to the first desiccator location.
- `PATCH /items/{id}` (manager) `ItemUpdate = { values{key: value}, serial? }` → `ItemOut`. Only the fields being changed. `location`, `parent` and `status` fields are changed with their own actions (400 otherwise); fixed fields are changed on the template.
- `DELETE /items/{id}` (manager) → 204 (its contents are unlinked, not deleted).
- `POST /items/bulk` (manager) `{ action: move|state_change|delete|link|unlink, item_ids[req], location_id?, parent_id?, state?, note? }` → `{ processed, failed, errors[] }`. **Atomic**.
- `POST /items/{id}/move` (manager) `{ location_id, note? }` → `ItemOut` (cascades to descendants). **A linked item cannot be moved** (400): move its container, or unlink it first.
- `POST /items/{id}/link` (manager) `{ parent_id }` → `ItemOut`. Allowed only if the parent's template lists the child's template and the link stays within that template's `max_count`; the child's subtree takes the parent's location. The same limit applies to `PUT …/children` (judged on the end state), to creating with `child_ids`, to raising a linked commercial card's quantity and to bringing a destroyed linked card back into service.
- `PUT /items/{id}/children` (manager) `{ child_ids[] }` → `ItemOut` — the container's contents, as the end state.
- `POST /items/{id}/unlink` (manager) `{ location_id? }` → `ItemOut`. It stays at the container's location unless `location_id` says where it now is.
- `POST /items/{id}/state` (manager) `{ state, note? }` → `ItemOut`. Note **required** into/out of `faulty`.
- `POST /items/{id}/documents` (manager) multipart: `file` (an upload) **or** `url` + `name`; optional `name`, `doc_type` → `DocumentOut`.
- `DELETE /items/{id}/documents/{doc_id}` (manager) → 204 (deletes the stored file).
- `POST /items/{id}/extras` (manager, setups) / `DELETE /items/{id}/extras/{id}`.

### Documents (uploads)
`DocumentOut = { id, name, doc_type, url, is_file, original_filename, content_type, size_bytes, field_id, created_at }`.
- `POST /uploads` (editor+) multipart `file` → `DocumentOut` — a **staged** upload, before the item exists. Put its id in a `files` field's value (`ItemCreate.values`, `ItemUpdate.values`, or a proposal's payload); the server attaches it. Unattached uploads are swept after 14 days.
- `GET /documents/{id}/download` (viewer+) → the file (authenticated; files are never served statically). `MAX_UPLOAD_MB` (default 50) caps an upload.

### Change requests (§9)
- `POST /change-requests` (viewer+, see roles) `{ action, item_id?, template_id?, item_type?, payload{}, description?, reason(req) }` → `ChangeRequestOut`. `description` is generated from the action and payload when omitted (the proposer is asked only *why*). Viewers: `move` only (403 otherwise).
  payload by action: `create`→`ItemCreate`; `update`→`ItemUpdate`; `move`→`{location_id, note?}`; `state_change`→`{state, note?}`; `link`→`{parent_id}`; `unlink`→`{location_id?}`; `delete`→`{}`; `template_create`→`TemplateCreate`; `template_update` (`template_id` required)→`TemplateUpdate`.
- `GET /change-requests?status=&mine=` → `ChangeRequestOut[]`; `GET /change-requests/{id}`.
- `POST /change-requests/{id}/approve` (manager) `{ note? }` → applies + notifies the proposer. A payload that no longer fits is a 400 (reject it).
- `POST /change-requests/{id}/reject` (manager) `{ note? }`.

`ChangeRequestOut = { id, action, item_id, template_id, item_type, item_name, payload, description, reason, status, proposed_by, reviewed_by, review_note, created_at, reviewed_at, proposer, reviewer }`.

### Inventory (§7, §12)
All figures are **sums of `Item.quantity`**. Definitions:
- **desiccator** — a card at a location with `is_desiccator`. The desiccator is a *place*: a card assembled into something that sits there is in it too;
- **available** — desiccator stock in state `built` or `ok`;
- **in use** — loose, elsewhere; **assembled** — inside an item elsewhere; **destroyed** cards count nowhere.

- `GET /inventory/summary` → `{ setups, assemblies, cards, cards_in_use, cards_desiccator, cards_available, faulty_items, pending_change_requests, low_stock_alerts, templates }`.
- `GET /inventory/cards?card_type=` → `InventoryGroup[]` — one per **card template**:
  `{ template_id, name, card_type, tracking, serial_prefix, total, available, desiccator, in_use, assembled, assembled_in_desiccator, faulty, records, available_serials[], min_quantity, is_low }` (`assembled_in_desiccator` = the part of `desiccator` inside assemblies).
- `GET /inventory/desiccator?card_type=` — the groups with desiccator stock.
- `GET /inventory/thresholds` / `GET /inventory/low-stock` → `ThresholdOut[] = { id, template_id, name, card_type, tracking, min_quantity, editor_email, current_quantity, is_low }` where `current_quantity` is the **available** stock.
- `POST /inventory/thresholds` (editor+) `{ template_id, min_quantity, editor_email? }` → `ThresholdOut` — sets (or replaces) the template's threshold.
- `DELETE /inventory/thresholds/{id}` (manager).

### Catalog — admin vocabularies
- `GET /catalog?category=project|industry|team&active_only=` → `CatalogOptionOut[] = { id, category, value, description, active, sort_order, usage_count, linked_ids[] }`.
- `POST /catalog`, `PATCH /catalog/{id}` (manager). Items hold the **id**, so a rename reaches them with no cascade.
- `PUT /catalog/{id}/links` (manager) `{ category, option_ids[] }` → `CatalogOptionOut` — this value's links to one *other* category, as the end state. Links are many-to-many and **two-way** (one row per pair), so they show from both ends.
- `GET /catalog/links` → `[{ a_id, b_id }]`.
- `DELETE /catalog/{id}` (manager) — 400 while used by an item or a template.

### Locations & the desiccator
- `GET /locations` → `LocationOut[] = { id, name, building, room, x, y, notes, is_desiccator, item_count }` (x, y in 0..100).
- `POST /locations`, `PATCH /locations/{id}` (editor+; only managers may change `is_desiccator`), `DELETE /locations/{id}` (manager; 400 while items are there).
- `PUT /locations/desiccator` (manager) `{ location_ids[] }` → `LocationOut[]` — the full set of desiccator locations.

### Map buildings
- `GET /map/buildings` (viewer+), `POST`/`PATCH /map/buildings/{id}` (editor+), `DELETE` (manager). All geometry 0..100.

### Graph
`GraphOut = { nodes: [{ id, label, type, state, card_type, serial, template_id, count }], edges: [{ source, target }], roots[] }`.
- `GET /graph/templates?root_template_id=` — the hierarchy the **templates** define (node ids are template ids, `count` = live units).
- `GET /graph?template_id=` — every live tree built from that template (one root per item).
- `GET /graph?root_id=&ancestors=` — one item's tree; `ancestors=true` adds the path up to the top.
- `GET /graph` — everything (small systems/scripts; the UI uses the views above).

### Audit (§10)
`AuditOut = { id, item_id, template_id, item_name, action, summary, details, user_id, user_name, created_at }`.
- `GET /audit?item_id=&template_id=&period=&mine=&action=&search=&limit=` — `period`: `day|week|month|half_year|year|all`; `mine=true` keeps only entries of items **linked to me** (I manage them or am their responsible) — nothing else, and nothing at all if I'm linked to no item.
- `GET /audit/my-items?period=` (viewer+) — shorthand for `mine=true`.
- `GET /audit/export?…same filters` → xlsx.

### Users (§8)
- `GET /users` (viewer+) → `UserOut[]`, `GET /users/managers` (viewer+) → `UserBrief[]`.
- `POST /users`, `PATCH /users/{id}`, `DELETE /users/{id}` (manager). Deleting a user also removes them from template fields that list them.

### Import / Export (§11)
- `GET /data/template?template_id=&type=` → xlsx: a *Read me* sheet, then **one sheet per template** (title `C-PRB Power Regulator Board`, …) whose header row is that template's creation fields (per-item + list fields, in order; not files), preceded by an optional `Serial` column and followed, for containers, by `Contents` (serials to place inside). Required headers are highlighted; each header's comment states its format and allowed values; list columns carry a dropdown.
- `POST /data/import` (manager) multipart `file` (.xlsx/.xlsm) → `{ created, by_template{name: n}, errors: [] }`. **All or nothing**: any invalid cell → 400 `{ detail, errors: [{ sheet, cell, row, column, error }] }` listing every bad cell, and nothing is saved.
- `GET /data/export?template_id=&type=` → xlsx, one sheet per template with readable names.

## Notification API (notification-service, port 8001)
- `GET /notifications?status=all|unread|read&limit=&offset=` → `Notification[]` (newest first) — **every** notification addressed to me, or only unread/read ones; page with `offset`. (`unread_only=true` still works.)
  `Notification = { id, type, title, body, payload, link, read, created_at }`.
  A `inventory.low_stock` alert's `payload.components[]` = `{ threshold_id, template_id, link, name, card_type, tracking, current_quantity, min_quantity, shortfall }`.
- `GET /notifications/count` → `{ total, unread, read }`; `GET /notifications/unread-count` → `{ count }`.
- `POST /notifications/{id}/read`, `POST /notifications/read-all` → 204.

## Event bus (Redis pub/sub, channel `lattice:events`)
core-api publishes `Event` JSON; notification-service consumes and fans out to
in-app notifications (one row per recipient with a `user_id`) + emails.

```
Event = {
  id, type, created_at, title, body, link,
  recipients: [{ user_id?, email?, role? }],
  payload: {}
}
```
`EventType`: `change_request.submitted | change_request.approved |
change_request.rejected | inventory.low_stock | item.state_changed`.

`inventory.low_stock` is one digest per recipient, listing the templates that
recipient is responsible for in `payload.components[]`.

## Database & migrations

The schema is owned by **Alembic** (`services/core-api/src/lattice_core/migrations`);
the API upgrades the database to head on start-up. A database created before
migrations existed is converted once, in a single transaction, by
`lattice_core/legacy_upgrade.py` (one template per distinct item name, fresh
serials, the old serial kept in a field, states/card types mapped, pending
proposals closed). Enums are checked VARCHARs (not native types) so a
vocabulary can change with one migration.

| Revision | What |
|---|---|
| `0001` | The template-driven model |
| `0002` | `template_children.min_count/max_count` (existing rows: 0 .. unlimited); `field_groups`, `field_group_fields` |

## First sign-in

The system ships **empty**. The only account created on first boot is the
bootstrap administrator (`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`,
default `admin@lattice.io` / `admin1234`). See [`USER_GUIDE.md`](USER_GUIDE.md)
for the order to set things up in.
