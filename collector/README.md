# Collector

> **Status: planned — no code yet.**

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
6. **Write raw rows** — insert into `metrics` and `logs`. Never derive
   or aggregate here — that is a separate concern.
7. **Respect `scrape_interval_seconds`** — wait the configured interval
   between polls for each service.

## What it will NOT do

- It will not detect incidents or anomalies (that is the detector's job).
- It will not modify any data it has already written.
- It will not import any code from the monitored applications.

## Planned files

```
collector/
├── collector.py      # main poll loop
├── parser.py         # Prometheus text-format parser
├── registry.py       # loads and validates services.yaml
└── Dockerfile        # scheduled container
```

## Key concept: Prometheus text format

Each line from `/metrics` looks like:

```
http_requests_total{method="GET",status="200"} 1234 1728900000000
```

That is: `metric_name{label_key="label_value"} numeric_value [timestamp_ms]`

The parser extracts `name`, `value`, and `labels` (as a dict) and
inserts one row into the `metrics` table per line.
