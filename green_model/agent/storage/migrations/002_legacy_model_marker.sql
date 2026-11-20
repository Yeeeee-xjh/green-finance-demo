ALTER TABLE model_runs ADD COLUMN legacy_note TEXT;

UPDATE model_runs
SET legacy_note = 'legacy_demo，不作为真实模型结果'
WHERE record_origin = 'legacy_demo'
  AND is_real_model_result = 0
  AND eligible_for_decision = 0;
