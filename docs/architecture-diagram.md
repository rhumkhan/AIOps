# AIOps Platform Architecture

This diagram shows the implemented Sentinel monitoring path. A second
application and DevOps dashboard/notifications are future extensions. The
rule evaluation currently runs in the registry-driven Python collector.

```mermaid
flowchart LR
    subgraph TARGET[Monitored application]
        SENTINEL[Sentinel]
        HEALTH[GET /health]
        METRICS[GET /metrics<br/>Prometheus text]
        FILES[Mounted text logs<br/>and JSON event files]
        SENTINEL --> HEALTH
        SENTINEL --> METRICS
        SENTINEL --> FILES
    end

    subgraph AIOPS[AIOps platform - Docker Compose]
        REGISTRY[Service registry<br/>services.yaml]
        COLLECTOR[Python collector<br/>health and metric polling<br/>rule evaluation]
        FORWARDER[OpenTelemetry Collector<br/>filelog parsing and OTLP export]
        API[FastAPI<br/>OTLP ingestion<br/>GET /incidents]
        DB[(PostgreSQL<br/>services, metrics, logs,<br/>otel_payloads, incidents)]

        REGISTRY -->|service URL, metric allow-list, rules| COLLECTOR
        API -->|store raw batch and normalize logs| DB
        COLLECTOR -->|upsert service and save metrics| DB
        DB -->|recent logs and metric samples| COLLECTOR
        COLLECTOR -->|create or update incidents| DB
        API <-->|read incident records| DB
    end

    HEALTH -->|HTTP probe| COLLECTOR
    METRICS -->|HTTP scrape| COLLECTOR
    FILES -->|read-only mounted log directory| FORWARDER
    FORWARDER -->|OTLP/HTTP protobuf<br/>POST /v1/logs| API

    SOURCE[Other OTLP source<br/>(future integration)] -.->|OTLP traces, metrics, logs| API
    API -.->|future| DASHBOARD[DevOps dashboard<br/>and notifications]

    classDef current fill:#e6f4ea,stroke:#188038,color:#173b22;
    classDef planned fill:#fff4e5,stroke:#d97706,color:#5c3b00,stroke-dasharray:5 5;
    class SENTINEL,HEALTH,METRICS,FILES,REGISTRY,COLLECTOR,FORWARDER,API,DB current;
    class SOURCE,DASHBOARD planned;
```

**Legend:** solid green elements and arrows show the demonstrated Sentinel
integration and implemented data paths. Dashed orange elements and arrows
show planned work. The API accepts OTLP traces and metrics and stores their
raw batches; normalized log storage is implemented. Trace/metric analysis,
integration of another application, a dashboard, and notifications have not
yet been demonstrated.

**Defense narration:** Sentinel exposes health and Prometheus metrics for the
Python collector to poll. A separate OpenTelemetry Collector tails Sentinel's
existing log files and sends them to the FastAPI OTLP endpoint. PostgreSQL
stores the observations. The Python collector evaluates configured
availability, metric-increase, and repeated-log rules and writes incidents.
The API exposes incidents for inspection. Additional app integrations and
DevOps notifications are future work.
