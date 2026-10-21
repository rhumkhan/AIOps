# Scenarios (Fault Injection)

> **Status: planned — no code yet.**

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
