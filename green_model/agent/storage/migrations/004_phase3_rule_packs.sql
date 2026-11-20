CREATE TABLE rule_packs (
    pack_id TEXT PRIMARY KEY,
    pack_name TEXT NOT NULL,
    industry TEXT,
    applicable_region TEXT,
    version_label TEXT NOT NULL,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE SET NULL,
    effective_at TEXT,
    expires_at TEXT,
    status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (pack_name, version_label, content_hash)
);

CREATE TABLE rule_pack_entries (
    pack_id TEXT NOT NULL REFERENCES rule_packs(pack_id) ON DELETE CASCADE,
    rule_version_id TEXT NOT NULL REFERENCES rule_versions(rule_version_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (pack_id, rule_version_id)
);

CREATE INDEX idx_rule_packs_industry ON rule_packs(industry, status);
CREATE INDEX idx_rule_pack_entries_sequence ON rule_pack_entries(pack_id, sequence_no);
