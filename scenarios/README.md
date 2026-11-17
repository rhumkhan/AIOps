# Scenarios (Fault Injection)

> **Status: a controlled log-rule demo is implemented; application fault scenarios remain planned.**

## Controlled log-rule demo

`send_log_rule_demo.py` sends three clearly marked synthetic ERROR records to
the AIOps OTLP API for the registered `sentinel` service. It does not modify or
fault Sentinel. The records carry `aiops.demo=true` and a run ID so they are
easy to identify in the logs and incident evidence. When the collector sees
the records, Sentinel's configured three-errors-in-five-minutes rule should
open an incident. The incident should resolve after those records leave the
five-minute window, provided no other matching errors arrive.

With AIOps and Sentinel running and Sentinel registered by the collector:

```powershell
docker compose cp ./scenarios/send_log_rule_demo.py api:/tmp/send_log_rule_demo.py
docker compose exec api python /tmp/send_log_rule_demo.py
```

If a `threshold_log_repeated_errors` incident is already open, wait for it to
resolve before running the script; otherwise the new records update that
incident's evidence instead of opening a separate one.

The script only emits telemetry. It does not write a `fault_labels` row because
the monitored application itself was not faulted.

## What this will do

The scenarios folder contains controlled fault-injection scripts.
Each script creates a specific, known failure in a monitored service,
records the start and end time, and writes a row to the `fault_labels`
table. That row becomes the **ground truth** used to evaluate the
platform's detection and root-cause ranking.

## Why fault injection?

The platform needs labelled data to answer:
- "Did the detector catch this incident?"
- "Did it rank the correct root cause first?"

Real production incidents are rare and not labelled. Fault injection
gives us controlled, repeatable failures with known answers.

## Responsibilities

1. **Inject a fault** — e.g., saturate CPU, exhaust memory, block a
   network port, corrupt a config file.
2. **Write a `fault_labels` row** — with `run_id`, `scenario`,
   `service_id`, `fault_type`, `start_time`, and `end_time`.
3. **Hold the fault** for a configured duration.
4. **Remove the fault** and record the end time.
5. **Never touch platform logic** — scenarios are external stimuli
   only. The platform must detect them on its own.

## Evaluation rule

Data is split by `run_id`, not by random rows. One complete injection
run either belongs to training or to the test set — never split across
both. This prevents the model from "seeing the future" during training.

## Planned files

```
scenarios/
├── run_scenario.py        # CLI entry point: python run_scenario.py <name>
├── scenarios/
│   ├── cpu_stress.py      # saturate one CPU core for N seconds
│   ├── memory_leak.py     # allocate memory until threshold
│   └── network_delay.py   # add latency to outbound connections
└── README.md              # this file
```

## Planned scenario catalogue

| Scenario | Fault type | What it tests |
|---|---|---|
| `cpu_stress_30s` | `cpu_overload` | Does the platform detect CPU spike? |
| `memory_leak_60s` | `memory_leak` | Does `memory_bytes` trigger an incident? |
| `network_delay_500ms` | `network_latency` | Does `latency_seconds` cross the threshold? |
| `health_endpoint_down` | `service_unavailable` | Does `up=0` open a critical incident? |
