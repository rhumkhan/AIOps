# AIOps Platform

An application-agnostic AIOps platform built as a Final Year Project for
BS Data Science.

## What it does

The platform monitors **other** applications (it never imports their code)
and provides:

1. **Telemetry collection** — polls Prometheus metrics, health endpoints,
   and JSON events, and accepts OpenTelemetry traces, metrics, and logs.
2. **Incident detection** — threshold baselines first, ML only if it
   proves better.
3. **Root-cause ranking** — lists *probable* root causes with evidence.
4. **Runbook retrieval** — RAG-based search over operational runbooks.
5. **Fix recommendation** — LLM-generated suggestions that cite their
   sources and may answer "insufficient evidence."
6. **Human-in-the-loop** — nothing executes automatically; a human
   approves every action, and every decision is written to an audit log.

## Quick start

```bash
# 1. Copy the environment template and fill in real values
cp .env.example .env

# 2. Start Postgres and the API
docker compose up --build

# 3. Verify
curl http://localhost:8000/health
```

## Project structure

```
aiops-platform/
├── api/           # FastAPI REST API
├── collector/     # Registry-driven raw telemetry collector
├── db/            # Database schema (init.sql)
├── docs/          # Telemetry contract, decision log
├── registry/      # Service definitions (YAML)
├── scenarios/     # Fault-injection scripts (planned)
└── tests/         # Automated tests
```

## Rules

See [PROJECT_RULES.md](PROJECT_RULES.md) for the full set of design
constraints and working agreements.

## Status

🟡 **Telemetry ingestion plus an initial availability rule.** The API has
an OTLP/HTTP protobuf receiver for traces, metrics, and logs; raw OTLP batches
are stored in PostgreSQL. A separate registry-driven collector polls
Prometheus metrics, health, and optional events. Failed health or metrics
checks create an evidence-backed availability incident, available through
`GET /incidents`. When both health and metrics checks recover, the collector
resolves the matching availability incident and records recovery evidence.
Registry-configured counter-increase rules can also create incidents with
measured window deltas, confidence boundaries, impact risk, and recommended
investigation steps. Registry-configured event rules can correlate recent
timestamped events into incidents, and registry-configured log rules can open
incidents when matching log levels repeat within a time window. Log-rule
incidents include matching records and explicit uncertainty about cause and
user impact. Broader threshold rules, acknowledgement workflows, notifications,
evaluation, fault scenarios, and the UI remain future work.

## Run the collector

Set `SENTINEL_URL` in `.env` to an address reachable from the collector
container (use `http://host.docker.internal:<port>` for an app running on
the host, or a Docker service name on the Compose network), then run:

```bash
docker compose --profile collector up --build
```

The collector polls only metrics named in each registry entry's
`metric_names` allow-list. It stores raw samples and events, opens an
availability incident when a health or metrics check fails, and resolves
that incident when both checks succeed again. Optional `metric_rules` support
`increase` detection over a configured lookback. Optional `event_rules` match
recent event metadata over a lookback window. Optional `log_rules` match log
levels and, optionally, a message substring from normalized OTLP logs within a
lookback window. Rule guidance stays in the service registry, and the collector
does not execute remediation.

Sentinel currently exposes `/health` and `/metrics`, but `/ops/events` returns
404. Its metrics are collected by the registry-driven scraper. To collect its
existing host-mounted log files without changing Sentinel, configure the
optional filelog forwarder below. Received OTLP log batches are retained in
`otel_payloads` and normalized into `logs` for registered services.

## Send OpenTelemetry data to AIOps

Configure an OpenTelemetry source to export OTLP/HTTP protobuf to the AIOps
API. For a source on the host, use `http://localhost:4318`; for a source in
the same Compose network, use `http://api:8000`. Set
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` and a resource service name, for
example `OTEL_SERVICE_NAME=sentinel`. The exporter sends to `/v1/traces`,
`/v1/metrics`, and `/v1/logs` under the configured base endpoint.

Accepted batches are stored losslessly in `otel_payloads`. For an existing
PostgreSQL volume created before this table was added, apply
`db/migrations/0002_otel_payloads.sql` once; the Docker entrypoint only runs
`db/init.sql` when it initializes a new data volume. With the default
database name and user, apply it using:

```powershell
docker compose exec db psql -U aiops -d aiops -f /migrations/0002_otel_payloads.sql
```

Replace `aiops` if `POSTGRES_USER` or `POSTGRES_DB` differs in `.env`.

For an existing database volume, apply the incident evidence migration once:

```powershell
docker compose exec db psql -U aiops -d aiops -f /migrations/0003_incident_evidence.sql
```

## Forward Sentinel's existing log files

Set `SENTINEL_LOGS_DIR` in `.env` to the host folder mounted by Sentinel's
containers (for example `D:/old_laptop/sentinel/logs`). Start Sentinel and
AIOps API/Postgres, then start the optional OpenTelemetry Collector filelog
forwarder:

```powershell
docker compose --profile sentinel-logs up -d sentinel-log-forwarder
```

The forwarder tails `sentinel_*.log` and `ops_events_*.jsonl`, labels them with
`service.name=sentinel`, and sends OTLP/HTTP logs to the AIOps API. The file
offsets persist in the `otel-log-state` volume. Inspect normalized records with:

```powershell
docker compose exec db psql -P pager=off -U aiops -d aiops -c "SELECT l.level, l.message, l.metadata, l.occurred_at, l.collected_at FROM logs l JOIN services s ON s.id = l.service_id WHERE s.name = 'sentinel' ORDER BY l.collected_at DESC, l.id DESC LIMIT 20;"
```

To confirm raw batches also arrived, run:

```powershell
docker compose exec db psql -P pager=off -U aiops -d aiops -c "SELECT received_at, record_count FROM otel_payloads WHERE signal = 'logs' AND service_names @> ARRAY['sentinel'] ORDER BY received_at DESC LIMIT 10;"
```

`GET http://localhost:8000/incidents` lists recent incidents after the
collector has detected an availability failure.
