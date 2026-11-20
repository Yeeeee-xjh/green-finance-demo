-- Phase 4.1: auditable model-inference decisions and explicit rule/model lineage.
-- Model predictions are screening evidence only and are never credit decisions.

CREATE TABLE model_prediction_records (
    prediction_id TEXT PRIMARY KEY,
    model_run_id TEXT NOT NULL REFERENCES model_runs(model_run_id) ON DELETE CASCADE,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    evidence_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    doc_id TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
    sentence_index INTEGER NOT NULL CHECK (sentence_index >= 0),
    sentence_sha256 TEXT NOT NULL,
    prediction_text TEXT NOT NULL,
    decision_status TEXT NOT NULL CHECK (decision_status IN (
        'accepted_for_review','screened_out','abstained'
    )),
    abstention_reason TEXT,
    green_relevance TEXT,
    green_relevance_confidence REAL,
    green_relevance_margin REAL,
    evidence_strength TEXT,
    evidence_strength_confidence REAL,
    claim_type TEXT,
    claim_type_confidence REAL,
    class_probabilities_json TEXT,
    inference_policy_version TEXT NOT NULL,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    is_real_model_result INTEGER NOT NULL DEFAULT 0 CHECK (is_real_model_result IN (0,1)),
    eligible_for_decision INTEGER NOT NULL DEFAULT 0 CHECK (eligible_for_decision IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (model_run_id, sentence_index, evidence_id),
    CHECK (eligible_for_decision = 0),
    CHECK (
        decision_status <> 'abstained'
        OR abstention_reason IS NOT NULL
    ),
    CHECK (
        record_origin <> 'legacy_demo'
        OR is_real_model_result = 0
    )
);

ALTER TABLE model_runs ADD COLUMN inference_policy_version TEXT;
ALTER TABLE model_runs ADD COLUMN runtime_metadata_json TEXT;

ALTER TABLE claim_signals
    ADD COLUMN prediction_id TEXT REFERENCES model_prediction_records(prediction_id) ON DELETE SET NULL;

ALTER TABLE risk_findings
    ADD COLUMN provenance_kind TEXT CHECK (provenance_kind IS NULL OR provenance_kind IN (
        'model','rule','deterministic_comparison','deterministic_bta','manual'
    ));
ALTER TABLE risk_findings
    ADD COLUMN model_run_id TEXT REFERENCES model_runs(model_run_id) ON DELETE SET NULL;
ALTER TABLE risk_findings ADD COLUMN inference_policy_version TEXT;

CREATE INDEX idx_model_predictions_case_run
    ON model_prediction_records(case_id, model_run_id, decision_status);
CREATE INDEX idx_risk_model_lineage
    ON risk_findings(model_run_id, provenance_kind, is_current);

