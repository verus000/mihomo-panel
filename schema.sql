CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscriptions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, url_enc TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours BETWEEN 1 AND 168),
 last_refresh TEXT, next_refresh TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), last_error TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS nodes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
 identity TEXT NOT NULL, name TEXT NOT NULL, country TEXT NOT NULL,
 manual_country INTEGER NOT NULL DEFAULT 0 CHECK(manual_country IN (0,1)),
 tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(tags) AND json_type(tags)='array'),
 protocol TEXT NOT NULL, config_enc TEXT NOT NULL,
 available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0,1)),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(subscription_id, identity)
);
CREATE INDEX IF NOT EXISTS nodes_sub_idx ON nodes(subscription_id);
CREATE TABLE IF NOT EXISTS services (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, port INTEGER NOT NULL UNIQUE CHECK(port BETWEEN 1024 AND 65535),
 username TEXT NOT NULL, password_enc TEXT NOT NULL,
 node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE RESTRICT,
 snapshot_enc TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 last_probe TEXT CHECK(last_probe IS NULL OR (json_valid(last_probe) AND json_type(last_probe)='object')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS audit_at_idx ON audit(at);
PRAGMA user_version=1;
