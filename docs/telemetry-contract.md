# Telemetry Contract (v0.2)

The agreement between the AIOps platform and every monitored application.
Platform code never contains app-specific logic; that lives in registry/.

## Required endpoints
| Endpoint | Format | Purpose |
|---|---|---|
| GET /metrics | Prometheus text | Numbers over time |
| GET /health | JSON | Is the app alive and are its dependencies okay |
| GET /ops/events?since=<time> (optional) | JSON list | Discrete events |

## OpenTelemetry push ingestion

The AIOps API accepts OTLP/HTTP protobuf batches at:

| Endpoint | Signal |
|---|---|
| POST /v1/traces | Traces/spans |
| POST /v1/metrics | Metrics/data points |
| POST /v1/logs | Logs/log records |

Send `Content-Type: application/x-protobuf` and configure the source exporter
to use `http/protobuf`. The default request body limit is 64 MiB; compressed
requests are not accepted yet. The API stores each accepted request body
losslessly in `otel_payloads`, along with the signal, receive time, record
count, resource attributes, and `service.name` values. Raw payloads are kept
alongside signal-specific normalized records where implemented.

Every source should set the OpenTelemetry resource attribute `service.name`
to its registered service name. For an app in the same Compose network, the
OTLP base endpoint is `http://api:8000`. For a source running on the host,
use `http://localhost:4318` (the Compose host port). With one base endpoint,
OTLP/HTTP exporters append `/v1/traces`, `/v1/metrics`, and `/v1/logs`.

OTLP log records from registered services are normalized into the `logs` table
with their source timestamp, severity, message, resource attributes, log
attributes, and trace/span identifiers when present. The service registry may
define `log_rules` over recent severity levels and an optional case-insensitive
message substring. A rule opens an incident only after its configured
occurrence count is reached within the lookback window; matching records are
attached as evidence. A log match is evidence of the reported event, not proof
of root cause or user impact.

## Canonical metrics
| Name | Meaning | Unit |
|---|---|---|
| up | Did the scrape succeed (set by the platform) | 0 or 1 |
| latency_seconds | Request or operation duration | seconds |
| error_rate | Failed requests / total requests | 0 to 1 |
| request_rate | Requests per second | per second |
| cpu_percent | Process CPU use | 0 to 100 |
| memory_bytes | Process memory | bytes |
| freshness_seconds | Age of the latest output or data | seconds |

## Health response
{"status": "ok", "service": "name", "version": "1.0.0",
 "uptime_seconds": 5231, "checks": {"model_file": {"ok": true}}}

## Event format (required: timestamp, service, component, event, status)
{"timestamp": "2026-10-13T12:30:10Z", "service": "sentinel-pipeline",
 "component": "data_source", "event": "fetch_completed", "status": "ok",
 "source": "acled", "duration_s": 4.2}

## Rules
- All metrics carry a service label. Timestamps are UTC ISO 8601.
- Required: /health and request_rate, error_rate, latency_seconds (or an adapter).
- Optional: events, CPU and memory, freshness, dependencies.
- Every contract change is recorded in docs/decision-log.md.
