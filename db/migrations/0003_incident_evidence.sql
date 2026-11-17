-- Store structured incident hypotheses and the evidence used to raise them.
ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS probable_root_cause TEXT,
    ADD COLUMN IF NOT EXISTS impact_assessment TEXT,
    ADD COLUMN IF NOT EXISTS recommended_action TEXT,
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN incidents.probable_root_cause IS
    'Evidence-based hypothesis; it is not a guaranteed diagnosis.';
COMMENT ON COLUMN incidents.impact_assessment IS
    'Likely user impact if the issue remains unresolved.';
COMMENT ON COLUMN incidents.recommended_action IS
    'Suggested investigation or action for a human operator.';
COMMENT ON COLUMN incidents.evidence IS
    'Structured telemetry observations supporting this incident.';
