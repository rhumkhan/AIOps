# Collector

> **Status: implemented - collection plus initial rule-based detection.**

## What this will do

The collector is a scheduled job that polls every service registered in
`registry/services.yaml` and writes raw telemetry into the database.

## Responsibilities

1. **Load the registry** — read `registry/services.yaml`, resolve
   `${ENV_VAR}` placeholders from the environment.
2. **Scrape `/metrics`** — fetch Prometheus text from each service's
   metrics endpoint, parse each line into `(name, value, labels)`.
3. **Filter by allow-list** — only store metrics whose names appear in
   the service's `metric_names` list. Discard the rest.
4. **Scrape `/health`** — fetch the JSON health response and update the
   `services.status` and `services.last_seen_at` columns.
5. **Scrape `/ops/events`** (optional) — fetch discrete events since the
   last scrape timestamp and write them to the `logs` table.
6. **Write raw rows** - insert incoming telemetry into `metrics` and `logs`.
7. **Evaluate configured rules** - apply metric, event, and log rules from the registry and attach matching telemetry as incident evidence.
8. **Respect `scrape_interval_seconds`** — wait the configured interval
   between polls for each service.

## What it will NOT do

- It does not run ML anomaly detection or claim root causes that available evidence does not establish.
- It will not modify any data it has already written.
- It will not import any code from the monitored applications.
- It will not execute remediation.

## Files

```
collector/
├── collector.py      # polling loop and PostgreSQL writes
├── parser.py         # Prometheus text-format parser
├── registry.py       # loads and validates services.yaml
├── requirements.txt  # collector dependencies
└── Dockerfile        # collector container
```

## Key concept: Prometheus text format

Each line from `/metrics` looks like:

```
http_requests_total{method="GET",status="200"} 1234 1728900000000
```

That is: `metric_name{label_key="label_value"} numeric_value [timestamp_ms]`

The parser extracts `name`, `value`, and `labels` (as a dict) and
inserts one row into the `metrics` table per line.

## Run

The collector is an opt-in Compose profile so the database and API can be
run without a monitored service. Configure `SENTINEL_URL` in `.env` to a
host or Docker network address reachable from the collector, then run
`docker compose --profile collector up --build`. The process reads
`DATABASE_URL` from `.env`, polls each registered service at its configured
interval, and logs scrape/database errors while continuing with other
services.
