-- Case-rule materialization and replaceable mock-rule governance.
-- Mock rules live in the same master tables as public rules, but can never
-- enter formal density statistics or produce a verified/pass conclusion.

ALTER TABLE source_manifest ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE industry_knowledge_items ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE industry_standard_links ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE indicator_definitions ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE threshold_definitions ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE permit_requirements ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE document_requirements ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE evidence_requirements ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE industry_risk_points ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE postloan_indicator_definitions ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE term_cards ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));

ALTER TABLE phase36_rule_items ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));
ALTER TABLE rule_application_mappings ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));

ALTER TABLE verification_items
    ADD COLUMN phase36_item_id TEXT REFERENCES phase36_rule_items(phase36_item_id) ON DELETE SET NULL;
ALTER TABLE verification_items
    ADD COLUMN application_mapping_id TEXT REFERENCES rule_application_mappings(application_mapping_id) ON DELETE SET NULL;
ALTER TABLE verification_items ADD COLUMN rule_module TEXT;
ALTER TABLE verification_items ADD COLUMN source_locator TEXT;
ALTER TABLE verification_items ADD COLUMN prescribed_task_type TEXT;
ALTER TABLE verification_items ADD COLUMN why_verify TEXT;
ALTER TABLE verification_items ADD COLUMN customer_manager_focus TEXT;
ALTER TABLE verification_items ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));

CREATE TABLE verification_requirement_links (
    verification_id TEXT NOT NULL
        REFERENCES verification_items(verification_id) ON DELETE CASCADE,
    evidence_requirement_id TEXT NOT NULL
        REFERENCES evidence_requirements(evidence_requirement_id) ON DELETE RESTRICT,
    requirement_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (requirement_status IN ('pending','matched','waived')),
    matched_evidence_id TEXT
        REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (verification_id, evidence_requirement_id)
);

CREATE TABLE mock_rule_batches (
    mock_batch_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    batch_label TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    replacement_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','removed','replaced')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE mock_rule_batch_items (
    mock_batch_id TEXT NOT NULL
        REFERENCES mock_rule_batches(mock_batch_id) ON DELETE CASCADE,
    record_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    delete_order INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (mock_batch_id, record_table, record_id)
);

CREATE INDEX idx_verification_phase36
    ON verification_items(case_id, phase36_item_id, is_current);
CREATE INDEX idx_verification_requirement_status
    ON verification_requirement_links(verification_id, requirement_status);
CREATE INDEX idx_mock_rule_batch_industry
    ON mock_rule_batches(industry_code, status);

CREATE TRIGGER trg_phase36_mock_insert_guard
BEFORE INSERT ON phase36_rule_items
WHEN NEW.is_mock = 1 AND (
    NEW.lineage_kind != 'simulation'
    OR NEW.formal_density_eligible != 0
    OR NEW.validation_status = 'qualified'
)
BEGIN
    SELECT RAISE(ABORT, 'mock rules must remain simulation and density-ineligible');
END;

CREATE TRIGGER trg_phase36_mock_update_guard
BEFORE UPDATE OF is_mock, lineage_kind, formal_density_eligible, validation_status
ON phase36_rule_items
WHEN NEW.is_mock = 1 AND (
    NEW.lineage_kind != 'simulation'
    OR NEW.formal_density_eligible != 0
    OR NEW.validation_status = 'qualified'
)
BEGIN
    SELECT RAISE(ABORT, 'mock rules must remain simulation and density-ineligible');
END;

CREATE TRIGGER trg_mock_mapping_guard
BEFORE INSERT ON rule_application_mappings
WHEN NEW.is_mock = 1 AND NOT EXISTS (
    SELECT 1 FROM phase36_rule_items i
    WHERE i.phase36_item_id = NEW.phase36_item_id AND i.is_mock = 1
)
BEGIN
    SELECT RAISE(ABORT, 'mock mapping must reference a mock rule item');
END;

CREATE TRIGGER trg_mock_verification_insert_guard
BEFORE INSERT ON verification_items
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed verification must remain pending verification');
END;

CREATE TRIGGER trg_mock_verification_update_guard
BEFORE UPDATE OF is_mock, status ON verification_items
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed verification must remain pending verification');
END;
