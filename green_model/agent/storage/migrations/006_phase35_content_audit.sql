-- Additive content audit: taxonomy/mapping counts never establish package depth.
ALTER TABLE industry_rule_profiles ADD COLUMN module_counts_json TEXT;
ALTER TABLE industry_rule_profiles ADD COLUMN coverage_review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (coverage_review_status IN ('unreviewed','reviewed'));
ALTER TABLE industry_activity_mappings ADD COLUMN relationship_role TEXT NOT NULL DEFAULT 'unreviewed' CHECK (relationship_role IN ('core','adjacent','unreviewed'));
ALTER TABLE industry_standard_links ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE indicator_definitions ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE threshold_definitions ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE threshold_definitions ADD COLUMN threshold_kind TEXT NOT NULL DEFAULT 'unreviewed' CHECK (threshold_kind IN ('explicit_numeric','non_numeric','unreviewed'));
ALTER TABLE permit_requirements ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE document_requirements ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE document_requirements ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived' CHECK (derivation_type IN ('policy_explicit','source_derived'));
ALTER TABLE evidence_requirements ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE evidence_requirements ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived' CHECK (derivation_type IN ('policy_explicit','source_derived'));
ALTER TABLE industry_risk_points ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE postloan_indicator_definitions ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));
ALTER TABLE postloan_indicator_definitions ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived' CHECK (derivation_type IN ('policy_explicit','source_derived'));
ALTER TABLE term_cards ADD COLUMN scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed'));

CREATE TABLE industry_knowledge_items (
    knowledge_id TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL,
    module TEXT NOT NULL CHECK (module IN ('process','equipment','route')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source_manifest(source_id) ON DELETE RESTRICT,
    source_locator TEXT NOT NULL,
    derivation_type TEXT NOT NULL CHECK (derivation_type IN ('policy_explicit','source_derived')),
    scope_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (scope_status IN ('core','adjacent','unreviewed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1)
);
CREATE INDEX idx_industry_knowledge_scope ON industry_knowledge_items(industry_code, module, scope_status);
