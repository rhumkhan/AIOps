"""Send marked synthetic errors through OTLP to demonstrate the log rule.

This creates demo telemetry only; it does not modify or fault the monitored app.
Run inside the AIOps API container after the service has been registered.
"""

from __future__ import annotations

import time
import urllib.request
import uuid

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest


def _attribute(attributes, key: str, value: str | bool) -> None:
    attribute = attributes.add()
    attribute.key = key
    if isinstance(value, bool):
        attribute.value.bool_value = value
    else:
        attribute.value.string_value = value


def main() -> None:
    run_id = str(uuid.uuid4())
    request = ExportLogsServiceRequest()
    resource_logs = request.resource_logs.add()
    _attribute(resource_logs.resource.attributes, "service.name", "sentinel")
    _attribute(resource_logs.resource.attributes, "aiops.demo.run_id", run_id)

    scope_logs = resource_logs.scope_logs.add()
    scope_logs.scope.name = "aiops-controlled-log-demo"
    timestamp_ns = time.time_ns()
    for index in range(1, 4):
        record = scope_logs.log_records.add()
        record.time_unix_nano = timestamp_ns + index
        record.severity_number = 17  # OTLP ERROR
        record.severity_text = "ERROR"
        record.body.string_value = f"[AIOPS-DEMO] controlled error record {index}/3"
        _attribute(record.attributes, "aiops.demo", True)
        _attribute(record.attributes, "aiops.demo.run_id", run_id)

    endpoint = "http://localhost:8000/v1/logs"
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"AIOps returned HTTP {response.status}")
        print(f"Accepted 3 clearly marked demo log records; run_id={run_id}")


if __name__ == "__main__":
    main()
