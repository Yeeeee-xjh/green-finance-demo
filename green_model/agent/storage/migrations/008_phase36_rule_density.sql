-- Phase 3.6 is additive.  It records density assessments and the business
-- mapping for every source-backed rule item; it never overwrites source files.
ALTER TABLE threshold_definitions ADD COLUMN applicable_scope TEXT;
ALTER TABLE threshold_definitions ADD COLUMN source_sha256 TEXT;

CREATE TABLE phase36_rule_items (
    phase36_item_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    module TEXT NOT NULL CHECK (module IN (
        'process','equipment','standard','indicator','threshold','permit',
        'document','evidence','risk','term','postloan','route'
    )),
    record_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    source_locator TEXT NOT NULL,
    lineage_kind TEXT NOT NULL CHECK (lineage_kind IN (
        'official_public_source','source_derived','simulation'
    )),
    formal_density_eligible INTEGER NOT NULL DEFAULT 0 CHECK (formal_density_eligible IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (record_table, record_id)
);

CREATE TABLE rule_application_mappings (
    application_mapping_id TEXT PRIMARY KEY,
    phase36_item_id TEXT NOT NULL REFERENCES phase36_rule_items(phase36_item_id) ON DELETE CASCADE,
    industry_code TEXT NOT NULL,
    verification_item_template TEXT NOT NULL,
    evidence_requirement_ids_json TEXT NOT NULL,
    task_type TEXT NOT NULL CHECK (task_type IN (
        '补件','冲突核实','规则核验','现场核验','贷后预警'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (phase36_item_id)
);

CREATE TABLE industry_density_assessments (
    density_assessment_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL UNIQUE,
    target_tier TEXT NOT NULL CHECK (target_tier IN ('first_tier','second_tier','base')),
    build_status TEXT NOT NULL CHECK (build_status IN (
        'base_only','depth_public_sources','partial_public_sources','pending'
    )),
    completion_percent INTEGER NOT NULL CHECK (completion_percent BETWEEN 0 AND 100),
    module_counts_json TEXT NOT NULL,
    unmet_gates_json TEXT NOT NULL,
    numeric_threshold_expected INTEGER NOT NULL DEFAULT 0 CHECK (numeric_threshold_expected IN (0,1)),
    numeric_threshold_status TEXT NOT NULL CHECK (numeric_threshold_status IN (
        'met','not_required','public_channel_not_obtained','insufficient'
    )),
    official_source_count INTEGER NOT NULL DEFAULT 0 CHECK (official_source_count >= 0),
    simulation_count INTEGER NOT NULL DEFAULT 0 CHECK (simulation_count >= 0),
    assessed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE simulation_rule_items (
    simulation_item_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    module TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    simulation_label TEXT NOT NULL DEFAULT 'separate simulation, not a formal rule',
    formal_density_eligible INTEGER NOT NULL DEFAULT 0 CHECK (formal_density_eligible = 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE INDEX idx_phase36_items_industry_module
    ON phase36_rule_items(industry_code, module, formal_density_eligible);
CREATE INDEX idx_rule_application_industry
    ON rule_application_mappings(industry_code, task_type);
CREATE INDEX idx_density_status
    ON industry_density_assessments(target_tier, build_status);
