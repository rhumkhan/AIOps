CREATE TABLE IF NOT EXISTS otel_payloads (
    id              BIGSERIAL       PRIMARY KEY,
    signal          TEXT            NOT NULL CHECK (signal IN ('traces', 'metrics', 'logs')),
    content_type    TEXT            NOT NULL,
    payload         BYTEA           NOT NULL,
    payload_sha256  CHAR(64)        NOT NULL,
    resources       JSONB           NOT NULL DEFAULT '[]',
    service_names   TEXT[]          NOT NULL DEFAULT '{}',
    record_count    INTEGER         NOT NULL CHECK (record_count >= 0),
    received_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otel_payloads_signal_time ON otel_payloads (signal, received_at);
CREATE INDEX IF NOT EXISTS idx_otel_payloads_service_names ON otel_payloads USING GIN (service_names);
CREATE INDEX IF NOT EXISTS idx_otel_payloads_resources ON otel_payloads USING GIN (resources);

COMMENT ON TABLE otel_payloads IS 'Lossless raw OTLP/HTTP protobuf batches, before normalization or incident analysis.';
COMMENT ON COLUMN otel_payloads.service_names IS 'service.name values extracted from each batch resource for lookup.';
COMMENT ON COLUMN otel_payloads.record_count IS 'Spans, metric data points, or log records in the batch.';
