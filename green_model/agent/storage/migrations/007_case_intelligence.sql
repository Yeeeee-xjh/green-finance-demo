CREATE TABLE analysis_runs (
    analysis_run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    run_kind TEXT NOT NULL CHECK (run_kind IN (
        'initial_assessment','supplement_reassessment','manual_rerun'
    )),
    engine_name TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    trigger_reason TEXT,
    base_case_revision INTEGER NOT NULL CHECK (base_case_revision >= 0),
    output_revision INTEGER CHECK (output_revision IS NULL OR output_revision >= 1),
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
    model_run_id TEXT REFERENCES model_runs(model_run_id) ON DELETE SET NULL,
    is_simulation INTEGER NOT NULL DEFAULT 0 CHECK (is_simulation IN (0,1)),
    coverage_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (case_id, engine_version, input_hash, run_kind, is_simulation)
);

CREATE TABLE claim_signals (
    claim_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
    evidence_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    model_run_id TEXT REFERENCES model_runs(model_run_id) ON DELETE SET NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT,
    green_relevance TEXT,
    evidence_strength TEXT,
    support_status TEXT NOT NULL CHECK (support_status IN (
        'supported','unsupported','contradicted','pending_review','model_unavailable'
    )),
    extraction_method TEXT NOT NULL,
    is_model_output INTEGER NOT NULL DEFAULT 0 CHECK (is_model_output IN (0,1)),
    requires_human_confirmation INTEGER NOT NULL DEFAULT 1 CHECK (requires_human_confirmation IN (0,1)),
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    CHECK (
        record_origin <> 'legacy_demo'
        OR (is_model_output = 0 AND requires_human_confirmation = 1)
    )
);

ALTER TABLE verification_items ADD COLUMN analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id) ON DELETE SET NULL;
ALTER TABLE verification_items ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1));

ALTER TABLE risk_findings ADD COLUMN analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id) ON DELETE SET NULL;
ALTER TABLE risk_findings ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1));

ALTER TABLE conflict_logs ADD COLUMN analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id) ON DELETE SET NULL;
ALTER TABLE conflict_logs ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1));

ALTER TABLE tasks ADD COLUMN analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN recompute_analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id) ON DELETE SET NULL;

CREATE TABLE analysis_run_documents (
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    input_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (analysis_run_id, doc_id)
);

CREATE INDEX idx_analysis_runs_case_status ON analysis_runs(case_id, status, created_at);
CREATE INDEX idx_claim_signals_case_current ON claim_signals(case_id, is_current, support_status);
CREATE INDEX idx_verification_current ON verification_items(case_id, is_current, status);
CREATE INDEX idx_risk_current ON risk_findings(case_id, is_current, risk_dimension);
CREATE INDEX idx_conflict_current ON conflict_logs(case_id, is_current, status);
