"""OTLP/HTTP protobuf receiver for raw OpenTelemetry telemetry batches."""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import os
from datetime import datetime, timezone

import psycopg2
from fastapi import APIRouter, Request
from google.protobuf import json_format
from google.protobuf.message import DecodeError, Message
from google.rpc.status_pb2 import Status
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from psycopg2.extras import Json
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

LOGGER = logging.getLogger("aiops.api.otlp")
router = APIRouter()
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
PROTOBUF_CONTENT_TYPE = "application/x-protobuf"


def _error(status_code: int, grpc_code: int, message: str) -> Response:
    body = Status(code=grpc_code, message=message).SerializeToString()
    return Response(body, status_code=status_code, media_type=PROTOBUF_CONTENT_TYPE)


async def _read_body(request: Request) -> bytes | Response:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_PAYLOAD_BYTES:
        return _error(413, 8, "OTLP request exceeds the 64 MiB limit")

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PAYLOAD_BYTES:
            return _error(413, 8, "OTLP request exceeds the 64 MiB limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _service_names(resources: list[Message]) -> list[str]:
    names: set[str] = set()
    for resource in resources:
        for attribute in resource.attributes:
            if attribute.key == "service.name" and attribute.value.WhichOneof("value") == "string_value":
                name = attribute.value.string_value.strip()
                if name:
                    names.add(name)
    return sorted(names)


def _serialize_resources(resources: list[Message]) -> list[dict]:
    return [json_format.MessageToDict(resource) for resource in resources]


def _trace_batch(request: ExportTraceServiceRequest) -> tuple[list[Message], int]:
    resources = [item.resource for item in request.resource_spans]
    count = sum(len(scope.spans) for item in request.resource_spans for scope in item.scope_spans)
    return resources, count


def _metric_batch(request: ExportMetricsServiceRequest) -> tuple[list[Message], int]:
    resources = [item.resource for item in request.resource_metrics]
    count = 0
    for resource_metrics in request.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                kind = metric.WhichOneof("data")
                if kind:
                    count += len(getattr(metric, kind).data_points)
    return resources, count


def _log_batch(request: ExportLogsServiceRequest) -> tuple[list[Message], int]:
    resources = [item.resource for item in request.resource_logs]
    count = sum(len(scope.log_records) for item in request.resource_logs for scope in item.scope_logs)
    return resources, count


def _any_value(value: Message) -> object:
    kind = value.WhichOneof("value")
    if kind in {"string_value", "bool_value", "int_value", "double_value"}:
        return getattr(value, kind)
    if kind == "bytes_value":
        return base64.b64encode(value.bytes_value).decode("ascii")
    if kind == "array_value":
        return [_any_value(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return {item.key: _any_value(item.value) for item in value.kvlist_value.values}
    return None


def _attribute_map(attributes) -> dict[str, object]:
    return {attribute.key: _any_value(attribute.value) for attribute in attributes}


def _log_level(severity_text: str, severity_number: int) -> str:
    text = severity_text.strip().upper()
    if text in {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}:
        return text
    if severity_number == 0:
        return "INFO"
    if severity_number >= 21:
        return "FATAL"
    if severity_number >= 17:
        return "ERROR"
    if severity_number >= 13:
        return "WARN"
    if severity_number >= 9:
        return "INFO"
    return "DEBUG"


def _log_timestamp(record: Message) -> datetime:
    timestamp_ns = record.time_unix_nano or record.observed_time_unix_nano
    if not timestamp_ns:
        return datetime.now(timezone.utc)
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=nanoseconds // 1_000)


def _normalized_log_rows(request: ExportLogsServiceRequest) -> list[tuple]:
    rows = []
    for resource_logs in request.resource_logs:
        resource_attributes = _attribute_map(resource_logs.resource.attributes)
        service_name = resource_attributes.get("service.name")
        for scope_logs in resource_logs.scope_logs:
            scope_name = scope_logs.scope.name
            for record in scope_logs.log_records:
                body = _any_value(record.body)
                if isinstance(body, str):
                    message = body
                elif body is None:
                    message = ""
                else:
                    message = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
                metadata = {
                    "resource": resource_attributes,
                    "attributes": _attribute_map(record.attributes),
                }
                if scope_name:
                    metadata["scope_name"] = scope_name
                if not isinstance(body, (str, type(None))):
                    metadata["body"] = body
                if record.trace_id:
                    metadata["trace_id"] = record.trace_id.hex()
                if record.span_id:
                    metadata["span_id"] = record.span_id.hex()
                rows.append((
                    service_name if isinstance(service_name, str) else None,
                    _log_level(record.severity_text, record.severity_number),
                    message,
                    metadata,
                    _log_timestamp(record),
                ))
    return rows


def _store_batch(
    signal: str,
    content_type: str,
    payload: bytes,
    resources: list[Message],
    count: int,
    normalized_logs: list[tuple] | None = None,
) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    resource_json = _serialize_resources(resources)
    service_names = _service_names(resources)
    digest = hashlib.sha256(payload).hexdigest()
    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO otel_payloads
                   (signal, content_type, payload, payload_sha256, resources, service_names, record_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (signal, content_type, psycopg2.Binary(payload), digest,
                 Json(resource_json), service_names, count),
            )
            if normalized_logs:
                rows_by_service: dict[str, list[tuple]] = {}
                for service_name, level, message, metadata, occurred_at in normalized_logs:
                    if service_name:
                        rows_by_service.setdefault(service_name, []).append(
                            (level, message, Json(metadata), occurred_at)
                        )
                for service_name, service_rows in rows_by_service.items():
                    cursor.execute("SELECT id FROM services WHERE name = %s", (service_name,))
                    service_row = cursor.fetchone()
                    if service_row is None:
                        LOGGER.warning(
                            "Stored OTLP logs for unregistered service %s as raw payload only",
                            service_name,
                        )
                        continue
                    cursor.executemany(
                        """INSERT INTO logs
                           (service_id, level, message, metadata, occurred_at)
                           VALUES (%s, %s, %s, %s, %s)""",
                        [
                            (service_row[0], level, message, metadata, occurred_at)
                            for level, message, metadata, occurred_at in service_rows
                        ],
                    )


async def _ingest(
    request: Request,
    signal: str,
    request_type: type[Message],
    response_type: type[Message],
    extract_batch,
) -> Response:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != PROTOBUF_CONTENT_TYPE:
        return _error(415, 3, "Use OTLP/HTTP with Content-Type: application/x-protobuf")
    content_encoding = request.headers.get("content-encoding", "identity").lower()
    if content_encoding not in {"", "identity"}:
        return _error(415, 3, "Compressed OTLP requests are not supported yet")

    payload = await _read_body(request)
    if isinstance(payload, Response):
        return payload

    message = request_type()
    try:
        message.ParseFromString(payload)
    except DecodeError:
        return _error(400, 3, "Invalid OTLP protobuf payload")

    resources, record_count = extract_batch(message)
    normalized_logs = _normalized_log_rows(message) if signal == "logs" else None
    try:
        await run_in_threadpool(
            _store_batch, signal, PROTOBUF_CONTENT_TYPE, payload, resources, record_count,
            normalized_logs,
        )
    except (psycopg2.Error, RuntimeError):
        LOGGER.exception("Could not store OTLP %s batch", signal)
        return _error(503, 14, "AIOps could not persist the telemetry batch")

    return Response(response_type().SerializeToString(), status_code=200, media_type=PROTOBUF_CONTENT_TYPE)


@router.post("/v1/traces")
async def ingest_traces(request: Request) -> Response:
    return await _ingest(
        request, "traces", ExportTraceServiceRequest, ExportTraceServiceResponse, _trace_batch
    )


@router.post("/v1/metrics")
async def ingest_metrics(request: Request) -> Response:
    return await _ingest(
        request, "metrics", ExportMetricsServiceRequest, ExportMetricsServiceResponse, _metric_batch
    )


@router.post("/v1/logs")
async def ingest_logs(request: Request) -> Response:
    return await _ingest(
        request, "logs", ExportLogsServiceRequest, ExportLogsServiceResponse, _log_batch
    )
