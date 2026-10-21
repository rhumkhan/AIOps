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