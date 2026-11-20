-- Phase 3.6 qualification is computed from validated source lineage.  These
-- guards make it impossible for simulations to be promoted to formal rules
-- and persist the evidence used by the density assessor.
ALTER TABLE threshold_definitions ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived'
    CHECK (derivation_type IN ('policy_explicit','source_derived'));
ALTER TABLE permit_requirements ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived'
    CHECK (derivation_type IN ('policy_explicit','source_derived'));
ALTER TABLE term_cards ADD COLUMN derivation_type TEXT NOT NULL DEFAULT 'source_derived'
    CHECK (derivation_type IN ('policy_explicit','source_derived'));

ALTER TABLE phase36_rule_items ADD COLUMN content_fingerprint TEXT;
ALTER TABLE phase36_rule_items ADD COLUMN source_sha256 TEXT;
ALTER TABLE phase36_rule_items ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (validation_status IN ('pending','qualified','rejected'));
ALTER TABLE phase36_rule_items ADD COLUMN validation_reasons_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE phase36_rule_items ADD COLUMN eligibility_policy_version TEXT NOT NULL DEFAULT 'phase36-v1';

ALTER TABLE industry_density_assessments ADD COLUMN assessment_policy_version TEXT NOT NULL DEFAULT 'phase36-v1';
ALTER TABLE industry_density_assessments ADD COLUMN threshold_basis_note TEXT;

CREATE TABLE rule_application_evidence_links (
    application_mapping_id TEXT NOT NULL
        REFERENCES rule_application_mappings(application_mapping_id) ON DELETE CASCADE,
    evidence_requirement_id TEXT NOT NULL
        REFERENCES evidence_requirements(evidence_requirement_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 1 CHECK (row_version >= 1),
    PRIMARY KEY (application_mapping_id, evidence_requirement_id)
);

CREATE UNIQUE INDEX idx_phase36_content_fingerprint
    ON phase36_rule_items(industry_code, module, content_fingerprint)
    WHERE content_fingerprint IS NOT NULL;
CREATE INDEX idx_rule_application_evidence
    ON rule_application_evidence_links(evidence_requirement_id);

-- New registrations always enter the fail-closed pending state.  A density
-- assessor must validate source lineage and evidence links before promotion.
CREATE TRIGGER trg_phase36_new_item_pending
BEFORE INSERT ON phase36_rule_items
WHEN NEW.formal_density_eligible != 0 OR NEW.validation_status != 'pending'
BEGIN
    SELECT RAISE(ABORT, 'new phase36 items must enter pending validation');
END;

CREATE TRIGGER trg_phase36_simulation_insert_guard
BEFORE INSERT ON phase36_rule_items
WHEN NEW.lineage_kind = 'simulation' AND NEW.formal_density_eligible != 0
BEGIN
    SELECT RAISE(ABORT, 'simulation rules cannot be formal-density eligible');
END;

CREATE TRIGGER trg_phase36_validation_coherence
BEFORE UPDATE OF lineage_kind, formal_density_eligible, validation_status,
                 content_fingerprint, source_sha256
ON phase36_rule_items
WHEN
    (NEW.validation_status = 'qualified' AND (
        NEW.formal_density_eligible != 1 OR NEW.lineage_kind = 'simulation'
        OR NEW.content_fingerprint IS NULL OR length(NEW.content_fingerprint) != 64
        OR NEW.source_sha256 IS NULL OR length(NEW.source_sha256) != 64
    ))
    OR
    (NEW.validation_status != 'qualified' AND NEW.formal_density_eligible != 0)
BEGIN
    SELECT RAISE(ABORT, 'phase36 validation status and eligibility are inconsistent');
END;

CREATE TRIGGER trg_phase36_simulation_update_guard
BEFORE UPDATE OF lineage_kind, formal_density_eligible ON phase36_rule_items
WHEN NEW.lineage_kind = 'simulation' AND NEW.formal_density_eligible != 0
BEGIN
    SELECT RAISE(ABORT, 'simulation rules cannot be formal-density eligible');
END;
