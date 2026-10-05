-- Schema of a pre-migration (create_all) Lattice database, kept verbatim so
-- test_legacy_upgrade.py can prove such a database converts cleanly.
CREATE TABLE users (
	id INTEGER NOT NULL,
	email VARCHAR(255) NOT NULL,
	full_name VARCHAR(255) NOT NULL,
	hashed_password VARCHAR(255) NOT NULL,
	role VARCHAR(7) NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at DATETIME NOT NULL,
	login_hint_visible BOOLEAN NOT NULL,
	login_hint_password VARCHAR(255),
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE TABLE locations (
	id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	building VARCHAR(255),
	room VARCHAR(255),
	x FLOAT NOT NULL,
	y FLOAT NOT NULL,
	notes TEXT,
	PRIMARY KEY (id)
);
CREATE INDEX ix_locations_name ON locations (name);
CREATE TABLE map_buildings (
	id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	x FLOAT NOT NULL,
	y FLOAT NOT NULL,
	width FLOAT NOT NULL,
	height FLOAT NOT NULL,
	color VARCHAR(32),
	notes TEXT,
	sort_order INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE TABLE catalog_options (
	id INTEGER NOT NULL,
	category VARCHAR(8) NOT NULL,
	value VARCHAR(255) NOT NULL,
	description VARCHAR(512),
	active BOOLEAN NOT NULL,
	sort_order INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_catalog_category_value UNIQUE (category, value)
);
CREATE INDEX ix_catalog_options_category ON catalog_options (category);
CREATE INDEX ix_catalog_options_value ON catalog_options (value);
CREATE TABLE items (
	id INTEGER NOT NULL,
	type VARCHAR(8) NOT NULL,
	is_template BOOLEAN NOT NULL,
	name VARCHAR(255) NOT NULL,
	industry VARCHAR(255),
	project VARCHAR(255),
	team VARCHAR(255),
	state VARCHAR(10) NOT NULL,
	description TEXT,
	dmz TEXT,
	parent_id INTEGER,
	location_id INTEGER,
	card_type VARCHAR(10),
	responsible VARCHAR(255),
	lead VARCHAR(255),
	production_date DATE,
	version VARCHAR(64),
	serial VARCHAR(128),
	storage_status VARCHAR(10),
	quantity INTEGER DEFAULT '1' NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(parent_id) REFERENCES items (id) ON DELETE SET NULL,
	FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE SET NULL
);
CREATE INDEX ix_items_version ON items (version);
CREATE INDEX ix_items_location_id ON items (location_id);
CREATE INDEX ix_items_type ON items (type);
CREATE INDEX ix_items_storage_status ON items (storage_status);
CREATE INDEX ix_items_name ON items (name);
CREATE INDEX ix_items_card_type ON items (card_type);
CREATE INDEX ix_items_project ON items (project);
CREATE INDEX ix_items_serial ON items (serial);
CREATE INDEX ix_items_is_template ON items (is_template);
CREATE INDEX ix_items_parent_id ON items (parent_id);
CREATE TABLE item_managers (
	item_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	PRIMARY KEY (item_id, user_id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE state_history (
	id INTEGER NOT NULL,
	item_id INTEGER NOT NULL,
	state VARCHAR(10) NOT NULL,
	note TEXT,
	changed_by INTEGER,
	changed_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE,
	FOREIGN KEY(changed_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_state_history_item_id ON state_history (item_id);
CREATE TABLE documents (
	id INTEGER NOT NULL,
	item_id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	url VARCHAR(1024),
	doc_type VARCHAR(64),
	PRIMARY KEY (id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
);
CREATE INDEX ix_documents_item_id ON documents (item_id);
CREATE TABLE extra_items (
	id INTEGER NOT NULL,
	setup_id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	company_part_number VARCHAR(128),
	serial VARCHAR(128),
	signed_by VARCHAR(255),
	PRIMARY KEY (id),
	FOREIGN KEY(setup_id) REFERENCES items (id) ON DELETE CASCADE
);
CREATE INDEX ix_extra_items_setup_id ON extra_items (setup_id);
CREATE TABLE change_requests (
	id INTEGER NOT NULL,
	action VARCHAR(12) NOT NULL,
	item_id INTEGER,
	item_type VARCHAR(8),
	item_name VARCHAR(255),
	payload JSON NOT NULL,
	description TEXT NOT NULL,
	reason TEXT NOT NULL,
	status VARCHAR(8) NOT NULL,
	proposed_by INTEGER NOT NULL,
	reviewed_by INTEGER,
	review_note TEXT,
	created_at DATETIME NOT NULL,
	reviewed_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE SET NULL,
	FOREIGN KEY(proposed_by) REFERENCES users (id),
	FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_change_requests_item_id ON change_requests (item_id);
CREATE INDEX ix_change_requests_status ON change_requests (status);
CREATE TABLE audit_log (
	id INTEGER NOT NULL,
	item_id INTEGER,
	item_name VARCHAR(255),
	action VARCHAR(64) NOT NULL,
	summary TEXT NOT NULL,
	details JSON NOT NULL,
	user_id INTEGER,
	user_name VARCHAR(255),
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE SET NULL,
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);
CREATE INDEX ix_audit_log_item_id ON audit_log (item_id);
CREATE TABLE stock_thresholds (
	id INTEGER NOT NULL,
	item_id INTEGER,
	card_type VARCHAR(10) NOT NULL,
	name VARCHAR(255),
	version VARCHAR(64),
	min_quantity INTEGER NOT NULL,
	editor_email VARCHAR(255),
	PRIMARY KEY (id),
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE SET NULL
);
CREATE INDEX ix_stock_thresholds_item_id ON stock_thresholds (item_id);
