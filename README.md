# AIOps Platform

An application-agnostic AIOps platform built as a Final Year Project for
BS Data Science.

## What it does

The platform monitors **other** applications (it never imports their code)
and provides:

1. **Telemetry collection** — polls Prometheus metrics, health endpoints,
   and JSON events from registered services.
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
├── collector/     # Telemetry collection job (planned)
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

🟡 **Phase 1 — Project skeleton.** API health endpoint only.
