-- Phase 4.6: industry-pack driven post-loan B-T-A monitoring.
-- Definition loading is deliberately task-free.  Only a comparable,
-- threshold-breaching evaluation can open a review task in application code.

ALTER TABLE postloan_indicator_definitions ADD COLUMN indicator_category TEXT
    CHECK (indicator_category IS NULL OR indicator_category IN (
        'funds_use','construction_progress','environmental_performance','compliance_event'
    ));
ALTER TABLE postloan_indicator_definitions ADD COLUMN comparison_direction TEXT
    CHECK (comparison_direction IS NULL OR comparison_direction IN (
        'higher_is_better','lower_is_better'
    ));
ALTER TABLE postloan_indicator_definitions ADD COLUMN warning_deviation_ratio TEXT;
ALTER TABLE postloan_indicator_definitions ADD COLUMN critical_deviation_ratio TEXT;
ALTER TABLE postloan_indicator_definitions ADD COLUMN statistical_scope TEXT;
ALTER TABLE postloan_indicator_definitions ADD COLUMN measurement_method TEXT;
ALTER TABLE postloan_indicator_definitions ADD COLUMN measurement_boundary TEXT;
ALTER TABLE postloan_indicator_definitions ADD COLUMN basis_version TEXT;

ALTER TABLE bta_indicators
    ADD COLUMN definition_id TEXT
        REFERENCES postloan_indicator_definitions(postloan_indicator_id) ON DELETE SET NULL;
ALTER TABLE bta_indicators ADD COLUMN indicator_category TEXT
    CHECK (indicator_category IS NULL OR indicator_category IN (
        'funds_use','construction_progress','environmental_performance','compliance_event'
    ));
ALTER TABLE bta_indicators ADD COLUMN warning_deviation_ratio TEXT;
ALTER TABLE bta_indicators ADD COLUMN critical_deviation_ratio TEXT;
ALTER TABLE bta_indicators ADD COLUMN measurement_method TEXT;
ALTER TABLE bta_indicators ADD COLUMN measurement_boundary TEXT;
ALTER TABLE bta_indicators ADD COLUMN basis_version TEXT;
ALTER TABLE bta_indicators
    ADD COLUMN source_manifest_id TEXT REFERENCES source_manifest(source_id) ON DELETE SET NULL;
ALTER TABLE bta_indicators ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));

ALTER TABLE bta_observations ADD COLUMN measurement_method TEXT;
ALTER TABLE bta_observations ADD COLUMN measurement_boundary TEXT;
ALTER TABLE bta_observations ADD COLUMN basis_version TEXT;
ALTER TABLE bta_observations ADD COLUMN is_mock INTEGER NOT NULL DEFAULT 0
    CHECK (is_mock IN (0,1));

CREATE TABLE postloan_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    indicator_id TEXT NOT NULL REFERENCES bta_indicators(indicator_id) ON DELETE CASCADE,
    semantic_key TEXT NOT NULL,
    baseline_observation_id TEXT REFERENCES bta_observations(observation_id) ON DELETE SET NULL,
    target_observation_id TEXT REFERENCES bta_observations(observation_id) ON DELETE SET NULL,
    actual_observation_id TEXT REFERENCES bta_observations(observation_id) ON DELETE SET NULL,
    comparability_status TEXT NOT NULL CHECK (comparability_status IN (
        'comparable','missing_series','basis_mismatch','invalid_numeric','threshold_not_configured'
    )),
    mismatch_fields_json TEXT NOT NULL DEFAULT '[]',
    target_actual_deviation_ratio TEXT,
    baseline_actual_change_ratio TEXT,
    adverse_direction INTEGER CHECK (adverse_direction IS NULL OR adverse_direction IN (0,1)),
    threshold_used TEXT,
    threshold_origin TEXT,
    breach_level TEXT NOT NULL CHECK (breach_level IN (
        'none','warning','critical','unknown'
    )),
    result_status TEXT NOT NULL CHECK (result_status IN (
        'pending_verification','ready_for_review','incomplete','basis_mismatch','pending_configuration'
    )),
    review_task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    engine_version TEXT NOT NULL,
    is_mock INTEGER NOT NULL DEFAULT 0 CHECK (is_mock IN (0,1)),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (case_id, semantic_key, engine_version)
);

CREATE INDEX idx_bta_definition_case
    ON bta_indicators(case_id, definition_id, indicator_category);
CREATE INDEX idx_bta_observation_series
    ON bta_observations(indicator_id, series_type, observed_at, created_at);
CREATE INDEX idx_postloan_evaluation_case
    ON postloan_evaluations(case_id, is_current, breach_level);

CREATE TRIGGER trg_mock_bta_indicator_status_insert
BEFORE INSERT ON bta_indicators
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed indicator must remain pending_verification');
END;

CREATE TRIGGER trg_mock_bta_indicator_status_update
BEFORE UPDATE OF status, is_mock ON bta_indicators
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed indicator must remain pending_verification');
END;

CREATE TRIGGER trg_bta_indicator_definition_mock_coherence
BEFORE INSERT ON bta_indicators
WHEN NEW.definition_id IS NOT NULL AND NEW.is_mock != COALESCE((
    SELECT is_mock FROM postloan_indicator_definitions
    WHERE postloan_indicator_id = NEW.definition_id
), -1)
BEGIN
    SELECT RAISE(ABORT, 'indicator mock flag must match its definition');
END;

CREATE TRIGGER trg_mock_bta_observation_status_insert
BEFORE INSERT ON bta_observations
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed observation must remain pending_verification');
END;

CREATE TRIGGER trg_mock_bta_observation_status_update
BEFORE UPDATE OF status, is_mock ON bta_observations
WHEN NEW.is_mock = 1 AND NEW.status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed observation must remain pending_verification');
END;

CREATE TRIGGER trg_mock_postloan_evaluation_status_insert
BEFORE INSERT ON postloan_evaluations
WHEN NEW.is_mock = 1 AND NEW.result_status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed evaluation must remain pending_verification');
END;

CREATE TRIGGER trg_mock_postloan_evaluation_status_update
BEFORE UPDATE OF result_status, is_mock ON postloan_evaluations
WHEN NEW.is_mock = 1 AND NEW.result_status != 'pending_verification'
BEGIN
    SELECT RAISE(ABORT, 'mock-backed evaluation must remain pending_verification');
END;
