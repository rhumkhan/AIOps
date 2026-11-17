# Midterm Defense Preparation

Use this as an honest outline for the current implementation. Update the
status and demo evidence after the latest local run; do not present planned
features as completed.

## Project in one sentence

An application-agnostic AIOps platform that collects telemetry from
registered services and is being developed to turn operational signals into
evidence-backed incidents for DevOps.

## Suggested slide order

1. **Problem and motivation** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â teams receive metrics, logs, and alerts from
   separate tools; diagnosing user-impacting failures takes time.
2. **Goal and scope** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â detect issues from available signals, report a
   probable root cause, describe likely user-impact risk, and recommend an
   action. The platform does not claim to observe signals a service does not
   provide.
3. **Architecture** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â registry-driven Prometheus pull and OTLP push feed the
   AIOps API and PostgreSQL. Raw telemetry is retained before analysis.
4. **Implementation completed** - FastAPI API, PostgreSQL, registry-driven Sentinel Prometheus collection, OTLP/HTTP receiver, availability and counter-increase rules, and a registry-driven repeated-error log rule. The file forwarder reads both plain-text logs and JSON event logs with source timestamps. On 2026-11-16, the log rule opened live incident 5 after repeated ACLED ERROR records. The records identify ACLED fetching as the affected area; the underlying cause remains unconfirmed.
5. **Live demonstration** - Show service registration, API and collector health, stored metrics, the availability incident lifecycle, the counter-increase incident, and the stored Sentinel logs. Apply migration `0003_incident_evidence.sql` and rebuild the collector before the demo.
6. **Evaluation plan** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â controlled failure scenarios with known start/end
   times and fault labels; measure detection, false positives, and time to
   detect before considering ML.
7. **Limitations and next work** - Detector coverage remains narrow. Incident 5 demonstrates repeated-error detection but does not identify why ACLED requests fail or prove user impact. Sentinel event ingestion through `/ops/events` remains unavailable; its files are forwarded instead. No frontend, DevOps notifications, broad root-cause ranking, or ML/RAG/LLM analysis is implemented. OTLP traces and metrics remain unverified end to end.

## Current architecture

```text
Monitored service
  ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Prometheus /metrics + JSON /health
  ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡    ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ registry-driven collector ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€šÃ‚Â
  ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ OTLP/HTTP protobuf (optional) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€šÃ‚Â¤
                                      v
                              AIOps API + PostgreSQL
                              raw signals ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ incidents
```

The Sentinel integration uses Prometheus scraping for metrics. Sentinel does not export OTLP directly; the separate filelog sidecar reads Sentinel's mounted files and sends OTLP logs into AIOps.

## Likely defense questions

- **Why is the platform application-agnostic?** App-specific endpoints,
  metric allow-lists, and labels live in a YAML registry; collector logic
  does not import monitored application code.
- **Why retain raw telemetry?** It preserves evidence and allows later
  normalization or analysis without losing the source payload.
- **Why start with thresholds?** They provide a transparent baseline that
  can be evaluated against controlled fault scenarios before adding ML.
- **Does it identify a guaranteed root cause?** No. It reports a probable
  cause based on available evidence and can state when evidence is
  insufficient.
- **How will you evaluate it?** Use labeled fault runs, split evaluation by
  run, and report detection delay, precision/recall, and false positives.
- **Does it automatically fix issues?** No. It recommends actions for a
  human operator; decisions remain auditable.

## Before presenting

- The incident migration is applied, and the API and collector are rebuilt.
- A live check confirmed `/health` and `/incidents` respond and that a failed
  availability check creates one incident without duplicating it each poll.
- The current incident evidence says the collector cannot reach
  `host.docker.internal:8001`; this proves a telemetry-path failure, not by
  itself a Sentinel user-facing outage. Explain that distinction if showing
  this incident.
- The collector now has a registry-configured rule for increases in
  `sentinel_ops_errors_total` over five minutes. The incident includes sample
  deltas and explicitly separates confidence in the measured increase from
  confidence in the underlying cause. Confirm the source exports this metric
  and that a live trigger was observed before claiming an end-to-end demo.
- Event rules are supported for registered services that expose a compatible
  events endpoint. Sentinel returns 404 at `/ops/events`; do not claim that
  AIOps is collecting Sentinel's individual events or logs.
- A live metric-rule incident recorded `sentinel_ops_errors_total` increasing
  from 1 to 2 over 11 samples in the five-minute window, with labels identifying
  `component=data_source`, `event=fetch_failed`. This supports that the
  operational-error signal increased; it does not prove a user-facing outage
  or establish the underlying cause.
- Before presenting, verify the target is reachable, review collector logs
  and database rows, and use a controlled failure relevant to the demo.
- Capture screenshots or a short screen recording as a fallback demo.
- Keep the implementation status and limitations slide accurate.
