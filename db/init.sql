-- ==============================================================
-- AIOps Platform — Database Schema
-- ==============================================================
-- Design principles (from PROJECT_RULES.md):
--   1. Store raw telemetry first; derive features/incidents later.
--   2. Ground truth lives in fault_labels, written by our own
--      fault-injection scenarios.
--   3. The platform never imports app code. Services are registered
--      via YAML and tracked here at runtime.
-- ==============================================================


-- ── 1. services ─────────────────────────────────────────
-- Runtime state of each monitored application.
-- The YAML registry (registry/services.yaml) declares *intent*
-- ("monitor this service at this URL"). This table tracks *reality*
-- ("when did we last hear from it? is it healthy?").

CREATE TABLE services (
    id              SERIAL          PRIMARY KEY,
    name            TEXT            NOT NULL UNIQUE,     -- matches registry key, e.g. "sentinel"
    base_url        TEXT            NOT NULL,            -- where to reach it, e.g. "http://sentinel:8000"
    status          TEXT            NOT NULL DEFAULT 'unknown'
                                   CHECK (status IN ('healthy', 'unhealthy', 'unknown')),
    registered_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ                          -- NULL until first successful poll
);

COMMENT ON TABLE  services              IS 'Runtime state of each monitored application.';
COMMENT ON COLUMN services.name         IS 'Unique service identifier, matches the key in registry/services.yaml.';
COMMENT ON COLUMN services.base_url     IS 'Root URL the collector uses to reach /metrics and /health.';
COMMENT ON COLUMN services.status       IS 'Last-known health: healthy | unhealthy | unknown.';
COMMENT ON COLUMN services.last_seen_at IS 'Timestamp of the last successful health-check response.';


-- ── 2. metrics ──────────────────────────────────────────
-- Raw numeric telemetry scraped from Prometheus /metrics endpoints.
-- One row per (service, metric name, label set, scrape instant).
-- BIGSERIAL because metrics are high-volume: many metrics × many
-- services × scrapes every 15–60 seconds.

CREATE TABLE metrics (
    id              BIGSERIAL       PRIMARY KEY,
    service_id      INTEGER         NOT NULL REFERENCES services (id),
    name            TEXT            NOT NULL,            -- canonical metric name, e.g. "http_requests_total"
    value           DOUBLE PRECISION NOT NULL,           -- the numeric value at this instant
    labels          JSONB           NOT NULL DEFAULT '{}',  -- Prometheus label set, e.g. {"method":"GET","status":"200"}
    collected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()  -- when the platform scraped this value
);

CREATE INDEX idx_metrics_service_time ON metrics (service_id, collected_at);
CREATE INDEX idx_metrics_name         ON metrics (name);

COMMENT ON TABLE  metrics               IS 'Raw numeric telemetry scraped from /metrics endpoints.';
COMMENT ON COLUMN metrics.name          IS 'Canonical metric name from docs/telemetry-contract.md.';
COMMENT ON COLUMN metrics.labels        IS 'Prometheus label key-value pairs stored as JSONB for flexible querying.';
COMMENT ON COLUMN metrics.collected_at  IS 'Scrape timestamp (platform clock, not the app clock).';


-- ── 3. logs ─────────────────────────────────────────────
-- Raw log / event entries received as JSON from monitored services.
-- Two timestamps: occurred_at (when the app says it happened) vs.
-- collected_at (when we ingested it). The difference matters for
-- incident correlation under network delays.

CREATE TABLE logs (
    id              BIGSERIAL       PRIMARY KEY,
    service_id      INTEGER         NOT NULL REFERENCES services (id),
    level           TEXT            NOT NULL
                                   CHECK (level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL')),
    message         TEXT            NOT NULL,            -- the log line or event summary
    metadata        JSONB           NOT NULL DEFAULT '{}',  -- additional structured fields from the event
    occurred_at     TIMESTAMPTZ     NOT NULL,            -- when the event happened (source clock)
    collected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()  -- when we ingested it (platform clock)
);

CREATE INDEX idx_logs_service_time ON logs (service_id, occurred_at);
CREATE INDEX idx_logs_level        ON logs (level);

COMMENT ON TABLE  logs                IS 'Raw log and event entries from monitored services.';
COMMENT ON COLUMN logs.level          IS 'Severity: DEBUG | INFO | WARN | ERROR | FATAL.';
COMMENT ON COLUMN logs.metadata       IS 'Structured fields beyond message, e.g. {"trace_id":"abc","user_id":42}.';
COMMENT ON COLUMN logs.occurred_at    IS 'Event timestamp reported by the source application.';
COMMENT ON COLUMN logs.collected_at   IS 'Ingestion timestamp on the platform clock.';


-- ── 4. incidents ────────────────────────────────────────
-- Detected incidents, derived from metrics and/or logs.
-- This is a "derived" table — it never holds raw telemetry.
-- Status tracks the human-in-the-loop lifecycle:
--   open → acknowledged → resolved.

CREATE TABLE incidents (
    id              SERIAL          PRIMARY KEY,
    service_id      INTEGER         NOT NULL REFERENCES services (id),
    title           TEXT            NOT NULL,            -- short summary, e.g. "CPU > 90 % for 5 min"
    description     TEXT,                                -- longer explanation with evidence
    severity        TEXT            NOT NULL
                                   CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    status          TEXT            NOT NULL DEFAULT 'open'
                                   CHECK (status IN ('open', 'acknowledged', 'resolved')),
    source          TEXT            NOT NULL,            -- what detected it, e.g. "threshold_cpu", "ml_anomaly"
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,                         -- NULL until a human acknowledges
    resolved_at     TIMESTAMPTZ                          -- NULL until resolved
);

CREATE INDEX idx_incidents_service  ON incidents (service_id);
CREATE INDEX idx_incidents_status   ON incidents (status);

COMMENT ON TABLE  incidents                  IS 'Incidents derived from telemetry analysis (threshold or ML).';
COMMENT ON COLUMN incidents.title            IS 'One-line summary suitable for alerts and dashboards.';
COMMENT ON COLUMN incidents.severity         IS 'Impact level: critical | high | medium | low.';
COMMENT ON COLUMN incidents.status           IS 'Lifecycle stage: open → acknowledged → resolved.';
COMMENT ON COLUMN incidents.source           IS 'Detection method that created this incident.';
COMMENT ON COLUMN incidents.acknowledged_at  IS 'Set when a human reviews and accepts the incident.';


-- ── 5. fault_labels ─────────────────────────────────────
-- Ground truth written by our own fault-injection scenarios.
-- Used to evaluate detection accuracy: did the platform detect the
-- fault, and did it rank the correct root cause?
-- run_id groups labels from the same injection run, supporting the
-- rule "split data by run, not by random rows."

CREATE TABLE fault_labels (
    id              SERIAL          PRIMARY KEY,
    run_id          TEXT            NOT NULL,            -- groups rows from one injection run (for train/test splits)
    scenario        TEXT            NOT NULL,            -- scenario name, e.g. "cpu_stress_30s"
    service_id      INTEGER         NOT NULL REFERENCES services (id),
    fault_type      TEXT            NOT NULL,            -- e.g. "cpu_overload", "memory_leak", "network_partition"
    start_time      TIMESTAMPTZ     NOT NULL,            -- when the fault was injected
    end_time        TIMESTAMPTZ     NOT NULL,            -- when the fault was removed
    notes           TEXT                                 -- free-form observations about this run
);

CREATE INDEX idx_fault_labels_run     ON fault_labels (run_id);
CREATE INDEX idx_fault_labels_service ON fault_labels (service_id);

COMMENT ON TABLE  fault_labels              IS 'Ground-truth labels from controlled fault-injection scenarios.';
COMMENT ON COLUMN fault_labels.run_id       IS 'Identifies one injection run; used for train/test splitting by run.';
COMMENT ON COLUMN fault_labels.scenario     IS 'Human-readable scenario name.';
COMMENT ON COLUMN fault_labels.fault_type   IS 'Category of injected fault.';
COMMENT ON COLUMN fault_labels.start_time   IS 'Moment the fault was activated.';
COMMENT ON COLUMN fault_labels.end_time     IS 'Moment the fault was deactivated.';
