# Decision Log

| # | Date | Decision | Why | Rejected alternative |
|---|---|---|---|---|
| 1 | 2026-10-14 | Initialize Git and .gitignore before creating .env | .env must be ignored from the moment it exists | Adding .gitignore later |
| 2 | 2026-10-14 | FastAPI for the backend | Async-ready, auto-generated /docs, type hints | Flask: no built-in async or API docs |
| 3 | 2026-10-14 | Get /health + Docker running before the schema | Fail fast: proves Docker works before debugging SQL | Schema first |
| 4 | 2026-10-14 | PostgreSQL 16, Python 3.11 | Stable, well supported | Newer versions with less library support |
| 5 | 2026-10-14 | Five separate tables | Different query patterns; incidents are derived | One unified events table |
| 6 | 2026-10-14 | JSONB for metric labels | Label sets vary per metric | Separate labels table: JOIN on millions of rows |
| 7 | 2026-10-14 | run_id in fault_labels | Split train/test by whole run, not random rows | Row-level splitting (leaks information) |
| 8 | 2026-10-14 | YAML registry plus a services table | Intent (Git) separate from live state (database) | Everything in the database |
| 9 | 2026-10-14 | Registry edited by hand, no auto-discovery | Simple and predictable; discovery is future work | Auto-discovery |
| 10 | 2026-10-14 | Unpinned dependency versions for now | Avoids rebuild breakage during development | Pin exact versions before submission |
| 11 | 2026-10-21 | ${ENV_VAR} substitution in services.yaml base_url | Same YAML file works in every environment; only .env changes | Separate YAML per environment (dev/staging/prod) — files diverge over time |
| 12 | 2026-10-21 | metric_names allow-list per service in registry | Collector stores only declared metrics; prevents DB bloat from internal Prometheus metrics | Store all metrics and filter at query time — wastes storage and slows queries |
| 13 | 2026-10-21 | Three separate test functions for /health | Each assertion failure points to the exact problem (status / body / content-type) | One test with all assertions — first failure hides the rest |
| 14 | 2026-10-22 | Implement the collector as an opt-in Compose profile | The raw telemetry path can be built and run independently; opt-in avoids scraping a missing target during the base API quick start | Start collection by default before a monitored service is configured |
| 15 | 2026-10-26 | Accept OTLP/HTTP protobuf for traces, metrics, and logs; persist raw batches | A standard push interface makes AIOps usable with OpenTelemetry sources while preserving original data for later normalization and analysis | Require each app to expose a custom vendor-specific ingest API or discard raw payloads after parsing |
| 16 | 2026-11-12 | Start incident detection with a generic availability rule and preserve evidence, probable cause, user-impact risk, and recommended action | Provides a transparent threshold baseline that can be demonstrated before adding broader rules or ML | Claim broad root-cause prediction before the platform has normalized signals and evaluated fault scenarios |
| 17 | 2026-11-12 | Resolve an availability incident after both health and metrics checks succeed, and append recovery evidence to that incident | Keeps the operational incident list aligned with observed service recovery while retaining the failure and recovery record | Leave recovered availability incidents open indefinitely or erase their history |
| 18 | 2026-11-12 | Define metric threshold rules in each service registry entry and keep the evaluator generic | Makes rules reusable across apps while keeping metric meaning, likely impact, and recommended investigation close to the service configuration | Hard-code Sentinel metric names and diagnosis into the collector |
| 19 | 2026-11-12 | Evaluate timestamped event rules against recently ingested event metadata | Preserves event-time evidence and detects fresh discrete failures without treating each repeated counter scrape as a new event | Infer a new event from an unchanged cumulative counter sample |
| 20 | 2026-11-12 | Add registry-driven log rules requiring repeated matching severities within a lookback window, with matched records attached as evidence | Turns normalized logs into explainable incidents while keeping service-specific patterns and guidance out of platform code | Treat every error log as an incident or infer root cause from severity alone |
| 21 | 2026-11-12 | Parse source timestamps from Sentinel file logs and repair initial backfill timestamps before evaluating rolling log windows | Prevents old file records from appearing new and triggering false incidents | Use file collection time as event time for backfilled logs |
| 22 | 2026-11-16 | Use separate filelog receivers for Sentinel plain-text logs and JSON event logs, each with a format-appropriate timestamp and severity parser | Keeps mixed file formats from producing parser errors and preserves source event time | Apply one strict parser to different file formats |
