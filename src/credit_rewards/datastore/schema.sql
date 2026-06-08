CREATE TABLE IF NOT EXISTS cards (
    card_key TEXT PRIMARY KEY,
    card_issuer TEXT NOT NULL,
    card_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    detail_json TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spend_categories (
    category_id INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL,
    category_group TEXT,
    subcategory_group TEXT,
    is_all INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS category_card_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    card_key TEXT NOT NULL,
    rule_json TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES spend_categories(category_id),
    FOREIGN KEY (card_key) REFERENCES cards(card_key)
);

CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(card_name);
CREATE INDEX IF NOT EXISTS idx_category_rules_cat ON category_card_rules(category_id);
CREATE INDEX IF NOT EXISTS idx_category_rules_card ON category_card_rules(card_key);

CREATE TABLE IF NOT EXISTS transfer_partners (
    transfer_partner_id INTEGER PRIMARY KEY,
    transfer_partner_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transfer_partner_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_partner_id INTEGER NOT NULL,
    rule_json TEXT NOT NULL,
    FOREIGN KEY (transfer_partner_id) REFERENCES transfer_partners(transfer_partner_id)
);

CREATE TABLE IF NOT EXISTS api_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skey TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    called_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS category_list_json (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS program_valuations (
    program_name TEXT PRIMARY KEY,
    earn_currency TEXT NOT NULL,
    cpp_default REAL NOT NULL,
    cpp_cash_floor REAL NOT NULL,
    is_cash_redeemable INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'rewardscc',
    benchmark_cpp_default REAL,
    benchmark_cpp_cash_floor REAL,
    benchmark_source TEXT,
    official_cpp REAL,
    official_cpp_sources_json TEXT,
    official_cpp_updated_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_program_valuations_source ON program_valuations(source);

CREATE TABLE IF NOT EXISTS analytics_devices (
    device_id TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    locale TEXT,
    user_agent TEXT,
    card_count INTEGER,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS analytics_sessions (
    session_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_sec INTEGER,
    FOREIGN KEY (device_id) REFERENCES analytics_devices(device_id)
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_device ON analytics_events(device_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_occurred ON analytics_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_analytics_devices_last_seen ON analytics_devices(last_seen_at);
