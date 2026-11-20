ALTER TABLE verification_items ADD COLUMN master_rule_type TEXT CHECK (
    master_rule_type IS NULL OR master_rule_type IN (
        'threshold','permit','document','evidence','industry_risk'
    )
);
ALTER TABLE verification_items ADD COLUMN master_rule_id TEXT;
ALTER TABLE verification_items ADD COLUMN source_manifest_id TEXT REFERENCES source_manifest(source_id) ON DELETE SET NULL;

CREATE INDEX idx_verification_master_rule
    ON verification_items(master_rule_type, master_rule_id);
