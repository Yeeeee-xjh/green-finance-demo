CREATE TABLE cases (
    case_id TEXT PRIMARY KEY,
    case_name TEXT,
    borrower_name TEXT,
    project_name TEXT,
    primary_industry TEXT,
    green_category TEXT,
    project_activity TEXT,
    enterprise_stage TEXT,
    project_stage TEXT,
    loan_stage TEXT,
    status TEXT CHECK (status IS NULL OR status IN (
        'draft','ingesting','parse_review','classifying','verifying',
        'action_required','human_review','monitoring','closed','failed'
    )),
    assignee TEXT,
    due_at TEXT,
    conclusion_status TEXT,
    current_revision INTEGER NOT NULL DEFAULT 0 CHECK (current_revision >= 0),
    failed_from_status TEXT,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    legacy_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE source_records (
    source_id TEXT PRIMARY KEY,
    source_type TEXT,
    title TEXT,
    issuer TEXT,
    source_url TEXT,
    published_at TEXT,
    effective_at TEXT,
    expires_at TEXT,
    accessed_at TEXT,
    local_path TEXT,
    sha256 TEXT,
    status TEXT CHECK (status IS NULL OR status IN (
        'candidate','verified','unavailable','superseded','invalid',
        'public_channel_not_obtained'
    )),
    authority_level TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_type TEXT,
    mime_type TEXT,
    source_kind TEXT,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE SET NULL,
    original_path TEXT,
    version_label TEXT,
    page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
    sha256 TEXT,
    parse_status TEXT CHECK (parse_status IS NULL OR parse_status IN (
        'uploaded','queued','parsing','parsed','needs_ocr','parse_failed','human_verified'
    )),
    parse_failure_reason TEXT,
    parent_doc_id TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    legacy_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE extraction_runs (
    extraction_run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    parser_name TEXT,
    parser_version TEXT,
    input_sha256 TEXT,
    config_hash TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    parsed_pages INTEGER CHECK (parsed_pages IS NULL OR parsed_pages >= 0),
    ocr_status TEXT,
    error_message TEXT,
    output_revision INTEGER CHECK (output_revision IS NULL OR output_revision >= 0),
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE project_facts (
    fact_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    extraction_run_id TEXT REFERENCES extraction_runs(extraction_run_id) ON DELETE SET NULL,
    fact_category TEXT,
    subject_id TEXT,
    scope_text TEXT,
    raw_value TEXT,
    normalized_value TEXT,
    normalized_scale INTEGER,
    unit TEXT,
    period_start TEXT,
    period_end TEXT,
    value_nature TEXT,
    method TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    match_basis TEXT,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE evidence_snippets (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    doc_id TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE SET NULL,
    extraction_run_id TEXT REFERENCES extraction_runs(extraction_run_id) ON DELETE SET NULL,
    page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
    bbox TEXT,
    locator_type TEXT,
    locator TEXT,
    raw_excerpt TEXT,
    text_sha256 TEXT,
    extraction_method TEXT,
    table_cell TEXT,
    verification_status TEXT CHECK (verification_status IS NULL OR verification_status IN (
        'satisfied','not_satisfied','pending_verification','evidence_conflict',
        'not_applicable','cannot_determine','attribute_only'
    )),
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    CHECK (doc_id IS NOT NULL OR source_id IS NOT NULL)
);

CREATE TABLE rule_versions (
    rule_version_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    rule_name TEXT,
    version_label TEXT,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE SET NULL,
    published_at TEXT,
    effective_at TEXT,
    expires_at TEXT,
    industry TEXT,
    activity TEXT,
    applicable_stage TEXT,
    requirement_text TEXT,
    threshold_json TEXT,
    evidence_requirement TEXT,
    is_bank_internal INTEGER NOT NULL DEFAULT 0 CHECK (is_bank_internal IN (0,1)),
    content_hash TEXT,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (rule_id, version_label, content_hash)
);

CREATE TABLE model_runs (
    model_run_id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,
    model_name TEXT,
    model_version TEXT,
    checkpoint_hash TEXT,
    config_hash TEXT,
    input_hash TEXT,
    output_json TEXT,
    confidence_definition TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    degradation_reason TEXT,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    is_real_model_result INTEGER NOT NULL DEFAULT 1 CHECK (is_real_model_result IN (0,1)),
    eligible_for_decision INTEGER NOT NULL DEFAULT 1 CHECK (eligible_for_decision IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    CHECK (
        record_origin <> 'legacy_demo'
        OR (is_real_model_result = 0 AND eligible_for_decision = 0)
    )
);

CREATE TABLE human_decisions (
    decision_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    target_type TEXT,
    target_id TEXT,
    decision TEXT,
    reason TEXT,
    actor TEXT,
    actor_role TEXT CHECK (actor_role IS NULL OR actor_role IN (
        'relationship_manager','industry_specialist','reviewer','approver',
        'team_lead','administrator','system','migration'
    )),
    decided_at TEXT,
    based_on_revision INTEGER CHECK (based_on_revision IS NULL OR based_on_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    task_type TEXT,
    trigger_reason TEXT,
    related_entity_type TEXT,
    related_entity_id TEXT,
    assignee TEXT,
    reviewer TEXT,
    due_at TEXT,
    status TEXT NOT NULL CHECK (status IN (
        'pending','in_progress','pending_review','closed','returned'
    )),
    closure_condition TEXT,
    handling_log_json TEXT,
    closing_evidence_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    recompute_run_id TEXT REFERENCES model_runs(model_run_id) ON DELETE SET NULL,
    closing_decision_id TEXT REFERENCES human_decisions(decision_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE verification_items (
    verification_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    risk_dimension TEXT,
    rule_version_id TEXT REFERENCES rule_versions(rule_version_id) ON DELETE SET NULL,
    requirement_text TEXT,
    status TEXT CHECK (status IS NULL OR status IN (
        'satisfied','not_satisfied','pending_verification','evidence_conflict',
        'not_applicable','cannot_determine','attribute_only'
    )),
    assignee TEXT,
    next_action TEXT,
    applicability_reason TEXT,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE risk_findings (
    finding_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    risk_dimension TEXT,
    trigger_type TEXT,
    risk_level TEXT CHECK (risk_level IS NULL OR risk_level IN (
        'low','medium','high','critical','unknown'
    )),
    review_priority INTEGER CHECK (review_priority IS NULL OR review_priority >= 0),
    finding_text TEXT,
    coverage_status TEXT,
    handling_status TEXT,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    is_model_result INTEGER NOT NULL DEFAULT 0 CHECK (is_model_result IN (0,1)),
    eligible_for_decision INTEGER NOT NULL DEFAULT 1 CHECK (eligible_for_decision IN (0,1)),
    legacy_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    CHECK (
        record_origin <> 'legacy_demo'
        OR (is_model_result = 0 AND eligible_for_decision = 0)
    )
);

CREATE TABLE conflict_logs (
    conflict_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    conflict_type TEXT,
    field_name TEXT,
    comparability_status TEXT,
    fact_a_id TEXT REFERENCES project_facts(fact_id) ON DELETE SET NULL,
    fact_b_id TEXT REFERENCES project_facts(fact_id) ON DELETE SET NULL,
    evidence_a_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    evidence_b_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    raw_value_a TEXT,
    raw_value_b TEXT,
    normalized_value_a TEXT,
    normalized_value_b TEXT,
    difference_value TEXT,
    difference_unit TEXT,
    ratio_denominator TEXT,
    denominator_value TEXT,
    difference_ratio TEXT,
    comparison_method TEXT,
    risk_level TEXT CHECK (risk_level IS NULL OR risk_level IN (
        'low','medium','high','critical','unknown'
    )),
    status TEXT,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE bta_indicators (
    indicator_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    indicator_name TEXT,
    direction TEXT,
    unit TEXT,
    statistical_scope TEXT,
    reporting_frequency TEXT,
    status TEXT,
    review_task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    record_origin TEXT NOT NULL CHECK (record_origin IN (
        'user_upload','public_source','system_derived','legacy_json','legacy_demo'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE bta_observations (
    observation_id TEXT PRIMARY KEY,
    indicator_id TEXT NOT NULL REFERENCES bta_indicators(indicator_id) ON DELETE CASCADE,
    series_type TEXT NOT NULL CHECK (series_type IN ('baseline','target','actual')),
    period_label TEXT,
    observed_at TEXT,
    raw_value TEXT,
    normalized_value TEXT,
    normalized_scale INTEGER,
    unit TEXT,
    statistical_scope TEXT,
    evidence_id TEXT REFERENCES evidence_snippets(evidence_id) ON DELETE SET NULL,
    source_id TEXT REFERENCES source_records(source_id) ON DELETE SET NULL,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE audit_logs (
    audit_id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    actor TEXT,
    actor_role TEXT CHECK (actor_role IS NULL OR actor_role IN (
        'relationship_manager','industry_specialist','reviewer','approver',
        'team_lead','administrator','system','migration'
    )),
    occurred_at TEXT NOT NULL,
    before_state TEXT,
    after_state TEXT,
    rule_version_id TEXT REFERENCES rule_versions(rule_version_id) ON DELETE SET NULL,
    model_run_id TEXT REFERENCES model_runs(model_run_id) ON DELETE SET NULL,
    file_hash TEXT,
    evidence_locator_json TEXT,
    details_json TEXT,
    correlation_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE report_snapshots (
    report_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    snapshot_revision INTEGER NOT NULL CHECK (snapshot_revision >= 0),
    generated_at TEXT,
    rule_versions_json TEXT,
    model_versions_json TEXT,
    source_manifest_hash TEXT,
    snapshot_json TEXT,
    snapshot_hash TEXT,
    pdf_path TEXT,
    pdf_hash TEXT,
    json_path TEXT,
    json_hash TEXT,
    status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (case_id, snapshot_revision)
);

CREATE TABLE fact_evidence_links (
    fact_id TEXT NOT NULL REFERENCES project_facts(fact_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_snippets(evidence_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (fact_id, evidence_id)
);

CREATE TABLE verification_fact_links (
    verification_id TEXT NOT NULL REFERENCES verification_items(verification_id) ON DELETE CASCADE,
    fact_id TEXT NOT NULL REFERENCES project_facts(fact_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (verification_id, fact_id)
);

CREATE TABLE verification_evidence_links (
    verification_id TEXT NOT NULL REFERENCES verification_items(verification_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_snippets(evidence_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (verification_id, evidence_id)
);

CREATE TABLE risk_evidence_links (
    finding_id TEXT NOT NULL REFERENCES risk_findings(finding_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_snippets(evidence_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (finding_id, evidence_id)
);

CREATE TABLE risk_rule_links (
    finding_id TEXT NOT NULL REFERENCES risk_findings(finding_id) ON DELETE CASCADE,
    rule_version_id TEXT NOT NULL REFERENCES rule_versions(rule_version_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (finding_id, rule_version_id)
);

CREATE TABLE risk_fact_links (
    finding_id TEXT NOT NULL REFERENCES risk_findings(finding_id) ON DELETE CASCADE,
    fact_id TEXT NOT NULL REFERENCES project_facts(fact_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (finding_id, fact_id)
);

CREATE TABLE task_evidence_links (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_snippets(evidence_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (task_id, evidence_id)
);

CREATE TABLE task_risk_links (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    finding_id TEXT NOT NULL REFERENCES risk_findings(finding_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (task_id, finding_id)
);

CREATE TABLE task_conflict_links (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    conflict_id TEXT NOT NULL REFERENCES conflict_logs(conflict_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (task_id, conflict_id)
);

CREATE TABLE task_verification_links (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    verification_id TEXT NOT NULL REFERENCES verification_items(verification_id) ON DELETE CASCADE,
    link_role TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (task_id, verification_id)
);

CREATE TABLE migration_batches (
    batch_id TEXT PRIMARY KEY,
    source_root TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE migration_records (
    migration_id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES migration_batches(batch_id) ON DELETE SET NULL,
    migration_key TEXT NOT NULL UNIQUE,
    importer_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_modified_at TEXT,
    migrated_at TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('migrated','skipped','failed')),
    details_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE INDEX idx_documents_case ON documents(case_id);
CREATE INDEX idx_documents_sha ON documents(sha256);
CREATE INDEX idx_extraction_case_doc ON extraction_runs(case_id, doc_id);
CREATE INDEX idx_facts_case ON project_facts(case_id);
CREATE INDEX idx_evidence_case_doc ON evidence_snippets(case_id, doc_id);
CREATE INDEX idx_verification_case_status ON verification_items(case_id, status);
CREATE INDEX idx_risks_case_level ON risk_findings(case_id, risk_level);
CREATE INDEX idx_conflicts_case_status ON conflict_logs(case_id, status);
CREATE INDEX idx_tasks_case_status ON tasks(case_id, status);
CREATE INDEX idx_bta_case ON bta_indicators(case_id);
CREATE INDEX idx_audit_case_time ON audit_logs(case_id, occurred_at);
CREATE INDEX idx_migration_source ON migration_records(source_path, source_sha256);

CREATE TRIGGER audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs are immutable');
END;

CREATE TRIGGER audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs are immutable');
END;
