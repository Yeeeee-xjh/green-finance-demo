CREATE TABLE source_manifest (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    issuer TEXT NOT NULL,
    document_no TEXT,
    standard_no TEXT,
    version_label TEXT,
    published_at TEXT,
    effective_at TEXT,
    expires_at TEXT,
    source_url TEXT,
    local_path TEXT,
    sha256 TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    authority_level TEXT NOT NULL,
    is_mandatory INTEGER CHECK (is_mandatory IS NULL OR is_mandatory IN (0,1)),
    formal_rule_eligible INTEGER NOT NULL DEFAULT 0 CHECK (formal_rule_eligible IN (0,1)),
    availability_status TEXT NOT NULL CHECK (availability_status IN (
        'full_text_obtained','official_summary_only','public_channel_not_obtained','superseded'
    )),
    limitation_note TEXT,
    superseded_by_source_id TEXT REFERENCES source_manifest(source_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (sha256, version_label)
);

CREATE TABLE industry_taxonomy (
    node_id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('section','division','group','class')),
    parent_node_id TEXT REFERENCES industry_taxonomy(node_id) ON DELETE RESTRICT,
    parent_code TEXT,
    section_code TEXT NOT NULL,
    official_description TEXT,
    included_activities TEXT,
    excluded_activities TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    source_version TEXT NOT NULL,
    source_url TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (source_version, code)
);

CREATE TABLE industry_rule_profiles (
    profile_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    taxonomy_node_id TEXT NOT NULL REFERENCES industry_taxonomy(node_id) ON DELETE CASCADE,
    priority_level INTEGER CHECK (priority_level IS NULL OR priority_level IN (1,2,3)),
    build_status TEXT NOT NULL CHECK (build_status IN (
        'base_only','depth_public_sources','partial_public_sources','pending'
    )),
    completion_percent INTEGER NOT NULL DEFAULT 0 CHECK (completion_percent BETWEEN 0 AND 100),
    industry_definition TEXT,
    boundary_text TEXT,
    typical_processes TEXT,
    common_project_types TEXT,
    core_equipment TEXT,
    technical_routes TEXT,
    midloan_review_focus TEXT,
    missing_modules_json TEXT,
    bank_rule_status TEXT NOT NULL DEFAULT '银行内部规则未接入，无法判断。',
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (industry_code, source_id)
);

CREATE TABLE standard_catalog (
    standard_id TEXT PRIMARY KEY,
    standard_no TEXT,
    standard_name TEXT NOT NULL,
    standard_type TEXT,
    issuer TEXT,
    effective_at TEXT,
    expires_at TEXT,
    full_text_status TEXT NOT NULL CHECK (full_text_status IN (
        'full_text_obtained','official_summary_only','reference_only','public_channel_not_obtained'
    )),
    public_scope_note TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE industry_standard_links (
    link_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    standard_id TEXT NOT NULL REFERENCES standard_catalog(standard_id) ON DELETE CASCADE,
    applicability TEXT NOT NULL,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (industry_code, standard_id, applicability)
);

CREATE TABLE indicator_definitions (
    indicator_definition_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    indicator_name TEXT NOT NULL,
    definition_text TEXT NOT NULL,
    formula_text TEXT,
    statistical_scope TEXT,
    unit TEXT,
    applicable_stage TEXT,
    derivation_type TEXT NOT NULL CHECK (derivation_type IN ('policy_explicit','source_derived')),
    formal_rule_eligible INTEGER NOT NULL DEFAULT 0 CHECK (formal_rule_eligible IN (0,1)),
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE threshold_definitions (
    threshold_id TEXT PRIMARY KEY,
    indicator_definition_id TEXT REFERENCES indicator_definitions(indicator_definition_id) ON DELETE CASCADE,
    industry_code TEXT NOT NULL,
    threshold_text TEXT NOT NULL,
    operator TEXT,
    threshold_value TEXT,
    unit TEXT,
    applicable_region TEXT,
    effective_at TEXT,
    expires_at TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE unit_conversion_rules (
    conversion_id TEXT PRIMARY KEY,
    industry_code TEXT,
    from_unit TEXT NOT NULL,
    to_unit TEXT NOT NULL,
    formula_text TEXT NOT NULL,
    applicability TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE permit_requirements (
    permit_requirement_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    permit_name TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    applicable_stage TEXT,
    applicable_region TEXT,
    status_note TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE document_requirements (
    document_requirement_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    document_name TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    mandatory_basis TEXT,
    applicable_stage TEXT,
    acceptable_alternatives TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE evidence_requirements (
    evidence_requirement_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    evidence_object TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    acceptable_evidence TEXT,
    unacceptable_substitution TEXT,
    applicable_stage TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE industry_risk_points (
    risk_point_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    risk_category TEXT NOT NULL,
    risk_title TEXT NOT NULL,
    risk_description TEXT NOT NULL,
    review_focus TEXT,
    derivation_type TEXT NOT NULL CHECK (derivation_type IN ('policy_explicit','source_derived')),
    formal_rule_eligible INTEGER NOT NULL DEFAULT 0 CHECK (formal_rule_eligible IN (0,1)),
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE postloan_indicator_definitions (
    postloan_indicator_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    indicator_name TEXT NOT NULL,
    definition_text TEXT NOT NULL,
    formula_text TEXT,
    unit TEXT,
    frequency TEXT,
    evidence_object TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE term_cards (
    term_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    term TEXT NOT NULL,
    definition_text TEXT NOT NULL,
    usage_note TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (industry_code, term, source_id)
);

CREATE TABLE green_catalog_activities (
    green_activity_id TEXT PRIMARY KEY,
    catalog_code TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    level1_name TEXT,
    level2_name TEXT,
    ghg_reduction_contribution INTEGER CHECK (ghg_reduction_contribution IS NULL OR ghg_reduction_contribution IN (0,1)),
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (catalog_code, source_id)
);

CREATE TABLE transition_catalog_activities (
    transition_activity_id TEXT PRIMARY KEY,
    activity_code TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    industry_scope TEXT NOT NULL,
    applicable_region TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (activity_code, applicable_region, source_id)
);

CREATE TABLE industry_activity_mappings (
    mapping_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    project_activity_name TEXT NOT NULL,
    mapping_domain TEXT NOT NULL CHECK (mapping_domain IN ('green_catalog','transition_catalog')),
    target_activity_id TEXT NOT NULL,
    mapping_type TEXT NOT NULL CHECK (mapping_type IN (
        'direct','partial','conditional','cannot_directly_map'
    )),
    applicable_conditions TEXT,
    non_applicable_conditions TEXT,
    evidence_requirement TEXT,
    applicable_region TEXT,
    source_page TEXT,
    source_file_hash TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    UNIQUE (industry_code, mapping_domain, target_activity_id, source_id)
);

CREATE TABLE regional_rule_overlays (
    overlay_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    region TEXT NOT NULL,
    overlay_name TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    effective_at TEXT,
    expires_at TEXT,
    source_page TEXT,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE rule_version_relations (
    relation_id TEXT PRIMARY KEY,
    old_source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    new_source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('replaces','amends','supplements','references')),
    relation_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE TABLE industry_build_logs (
    build_log_id TEXT PRIMARY KEY,
    industry_code TEXT,
    build_stage TEXT NOT NULL,
    build_status TEXT NOT NULL,
    message TEXT NOT NULL,
    source_id TEXT REFERENCES source_manifest(source_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);

CREATE INDEX idx_industry_taxonomy_parent ON industry_taxonomy(parent_node_id, sort_order);
CREATE INDEX idx_industry_taxonomy_lookup ON industry_taxonomy(code, name, level);
CREATE INDEX idx_industry_profiles_priority ON industry_rule_profiles(priority_level, build_status);
CREATE INDEX idx_industry_standard_links_code ON industry_standard_links(industry_code);
CREATE INDEX idx_indicator_definitions_code ON indicator_definitions(industry_code);
CREATE INDEX idx_threshold_definitions_code ON threshold_definitions(industry_code);
CREATE INDEX idx_permit_requirements_code ON permit_requirements(industry_code);
CREATE INDEX idx_document_requirements_code ON document_requirements(industry_code);
CREATE INDEX idx_evidence_requirements_code ON evidence_requirements(industry_code);
CREATE INDEX idx_industry_risk_points_code ON industry_risk_points(industry_code);
CREATE INDEX idx_postloan_indicators_code ON postloan_indicator_definitions(industry_code);
CREATE INDEX idx_term_cards_code ON term_cards(industry_code);
CREATE INDEX idx_activity_mappings_code ON industry_activity_mappings(industry_code, mapping_domain);
CREATE INDEX idx_regional_overlays_code ON regional_rule_overlays(industry_code, region);
CREATE INDEX idx_source_manifest_status ON source_manifest(availability_status, formal_rule_eligible);
