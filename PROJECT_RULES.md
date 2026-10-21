# Project Rules

These rules govern every decision in the AIOps platform. Every session
starts by reading this file.

## Platform independence

- The platform is independent of the applications it monitors. It never
  imports their code.
- Everything app-specific lives in `registry/` (YAML) and metric
  mappings, never in platform logic.

## Telemetry contract

- Applications are read only through `docs/telemetry-contract.md`:
  Prometheus text at `/metrics`, JSON at `/health`, JSON events.
- Use the canonical metric names defined there.

## Data architecture

- Store raw telemetry first. Derive features, incidents, and predictions
  in separate tables.
- Ground truth comes from my own fault scenarios, written to a
  `fault_labels` table (scenario, target service, start time, end time).

## Evaluation

- Build simple threshold baselines before ML. ML must prove it beats
  them.
- Split data by run, not by random rows.

## LLM guardrails

- The LLM only sees retrieved evidence and runbook text, must cite its
  source, and may answer "insufficient evidence."

## Human-in-the-loop

- Nothing executes automatically. A human approves, and every decision
  is written to the audit log.

## Wording

- "Probable root cause" and "recommended action", never "guaranteed."

## Scope

- AIOps is the main project. Do not suggest changes to any other
  application.

## Session protocol

- Each new session must start by reading `PROJECT_RULES.md` and
  `docs/decision-log.md`.
