"""Poll registered services and persist raw telemetry in PostgreSQL."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import Json

from parser import Sample, parse_prometheus_text
from registry import EventRule, LogRule, MetricRule, ServiceConfig, load_registry

LOGGER = logging.getLogger("aiops.collector")
TIMEOUT_SECONDS = 5


def _get(url: str, accept: str) -> tuple[bytes, str]:
    request = Request(url, headers={"Accept": accept, "User-Agent": "aiops-collector/0.1"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get("Content-Type", "")


def _fetch_json(url: str) -> object:
    body, _ = _get(url, "application/json")
    return json.loads(body.decode("utf-8"))


def _upsert_service(cursor, service: ServiceConfig) -> int:
    cursor.execute(
        """INSERT INTO services (name, base_url) VALUES (%s, %s)
           ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url
           RETURNING id""",
        (service.name, service.base_url),
    )
    return cursor.fetchone()[0]


def _labels(service: ServiceConfig, sample_labels: dict[str, str] | None = None) -> dict[str, str]:
    result = dict(service.default_labels)
    result["service"] = service.name
    result.update(sample_labels or {})
    result["service"] = service.name
    return result


def _store_metrics(cursor, service_id: int, service: ServiceConfig, samples: list[Sample], scraped_ok: bool) -> None:
    rows = []
    for sample in samples:
        if sample.name == "up" or sample.name not in service.metric_names:
            continue
        rows.append((service_id, sample.name, sample.value, Json(_labels(service, sample.labels))))
    if "up" in service.metric_names:
        rows.append((service_id, "up", 1.0 if scraped_ok else 0.0, Json(_labels(service))))
    cursor.executemany(
        "INSERT INTO metrics (service_id, name, value, labels) VALUES (%s, %s, %s, %s)",
        rows,
    )


def _event_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("event timestamp must be an ISO 8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("event timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _event_level(event: dict) -> str:
    status = str(event.get("status", "")).lower()
    level = str(event.get("level", "")).upper()
    if level in {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}:
        return level
    if status in {"error", "failed", "failure", "critical"}:
        return "ERROR"
    if status in {"warn", "warning"}:
        return "WARN"
    return "INFO"


def _store_events(cursor, service_id: int, service: ServiceConfig, events: object) -> None:
    if not isinstance(events, list):
        raise ValueError("events endpoint must return a JSON list")
    rows = []
    for event in events:
        if not isinstance(event, dict):
            LOGGER.warning("Skipping non-object event from %s", service.name)
            continue
        try:
            required = ("timestamp", "service", "component", "event", "status")
            if any(not isinstance(event.get(key), str) or not event[key] for key in required):
                raise ValueError("event is missing a required string field")
            occurred_at = _event_time(event["timestamp"])
            message = f"{event['component']}.{event['event']}: {event['status']}"
            rows.append((service_id, _event_level(event), message, Json(event), occurred_at))
        except (ValueError, TypeError) as exc:
            LOGGER.warning("Skipping invalid event from %s: %s", service.name, exc)
    cursor.executemany(
        """INSERT INTO logs (service_id, level, message, metadata, occurred_at)
           VALUES (%s, %s, %s, %s, %s)""",
        rows,
    )


def _open_availability_incident(
    cursor,
    service_id: int,
    service: ServiceConfig,
    health_ok: bool,
    health_status: str | None,
    health_error: str | None,
    scrape_ok: bool,
    scrape_error: str | None,
) -> None:
    """Open one active incident when a service health or metrics check fails."""
    if health_ok and scrape_ok:
        return

    cursor.execute(
        """SELECT id FROM incidents
           WHERE service_id = %s AND source = 'threshold_availability'
             AND status IN ('open', 'acknowledged')
           LIMIT 1""",
        (service_id,),
    )
    if cursor.fetchone():
        return

    severity = "high" if not health_ok else "medium"
    probable_root_cause = (
        "The health check or metrics endpoint failed. Available evidence does not yet "
        "distinguish an application failure from a dependency, endpoint, or network issue."
    )
    impact_assessment = (
        "If the application itself is unavailable, users may experience failed requests. "
        "If only telemetry collection failed, user impact is unconfirmed."
    )
    recommended_action = (
        "Check the service process, its health and metrics endpoints, dependencies, and "
        "the network path from the AIOps collector."
    )
    evidence = {
        "health_ok": health_ok,
        "health_status": health_status,
        "health_error": health_error,
        "health_url": service.base_url + service.endpoints["health"],
        "metrics_scrape_ok": scrape_ok,
        "metrics_error": scrape_error,
        "metrics_url": service.base_url + service.endpoints["metrics"],
    }
    cursor.execute(
        """INSERT INTO incidents
           (service_id, title, description, severity, source,
            probable_root_cause, impact_assessment, recommended_action, evidence)
           VALUES (%s, %s, %s, %s, 'threshold_availability', %s, %s, %s, %s)""",
        (
            service_id,
            f"{service.name} availability check failed",
            "A registered service failed its health check or Prometheus metrics scrape.",
            severity,
            probable_root_cause,
            impact_assessment,
            recommended_action,
            Json(evidence),
        ),
    )


def _resolve_availability_incident(
    cursor,
    service_id: int,
    service: ServiceConfig,
) -> None:
    """Resolve active availability incidents after both checks recover."""
    recovery_evidence = {
        "recovery": {
            "health_ok": True,
            "health_url": service.base_url + service.endpoints["health"],
            "metrics_scrape_ok": True,
            "metrics_url": service.base_url + service.endpoints["metrics"],
        }
    }
    cursor.execute(
        """UPDATE incidents
           SET status = 'resolved', resolved_at = NOW(),
               evidence = evidence || %s::jsonb
           WHERE service_id = %s AND source = 'threshold_availability'
             AND status IN ('open', 'acknowledged')
           RETURNING id""",
        (Json(recovery_evidence), service_id),
    )
    resolved_ids = [row[0] for row in cursor.fetchall()]
    if resolved_ids:
        LOGGER.info(
            "Resolved availability incident(s) %s for %s after health and metrics checks recovered",
            resolved_ids,
            service.name,
        )


def _evaluate_metric_rule(cursor, service_id: int, service: ServiceConfig, rule: MetricRule) -> None:
    """Evaluate an allow-listed counter increase rule and maintain its incident."""
    cursor.execute(
        """SELECT labels, value, collected_at, id
           FROM metrics
           WHERE service_id = %s AND name = %s
             AND collected_at >= NOW() - (%s * INTERVAL '1 second')
           ORDER BY labels, collected_at, id""",
        (service_id, rule.metric, rule.lookback_seconds),
    )
    samples_by_labels: dict[str, list[tuple[float, datetime]]] = {}
    labels_by_key: dict[str, dict] = {}
    for labels, value, collected_at, _sample_id in cursor.fetchall():
        label_set = labels if isinstance(labels, dict) else {}
        key = json.dumps(label_set, sort_keys=True)
        labels_by_key[key] = label_set
        samples_by_labels.setdefault(key, []).append((float(value), collected_at))

    evaluated_series: list[dict] = []
    breached_series: list[dict] = []
    counter_reset = False
    for key, samples in samples_by_labels.items():
        if len(samples) < 2:
            continue
        first_value, first_time = samples[0]
        latest_value, latest_time = samples[-1]
        increase = latest_value - first_value
        observation = {
            "labels": labels_by_key[key],
            "first_value": first_value,
            "first_sample_at": first_time.isoformat(),
            "latest_value": latest_value,
            "latest_sample_at": latest_time.isoformat(),
            "increase": increase,
            "sample_count": len(samples),
        }
        if increase < 0:
            observation["counter_reset"] = True
            counter_reset = True
            continue
        evaluated_series.append(observation)
        if increase > rule.threshold:
            breached_series.append(observation)

    if not evaluated_series and not breached_series:
        # A missing or reset counter is not evidence that the condition cleared.
        return

    source = f"threshold_metric_{rule.name}"
    evidence = {
        "rule": rule.name,
        "metric": rule.metric,
        "detection": rule.detection,
        "lookback_seconds": rule.lookback_seconds,
        "threshold": rule.threshold,
        "breached": bool(breached_series),
        "breached_series": breached_series,
        "evaluated_series": evaluated_series,
        "counter_reset_observed": counter_reset,
        "confidence": {
            "observed_signal": "high",
            "probable_root_cause": "low",
            "reason": (
                "The counter increase is directly measured, but this metric alone does not identify "
                "the underlying component or prove user impact."
            ),
        },
    }

    cursor.execute(
        """SELECT id FROM incidents
           WHERE service_id = %s AND source = %s
             AND status IN ('open', 'acknowledged')
           LIMIT 1""",
        (service_id, source),
    )
    active_incident = cursor.fetchone()

    if breached_series:
        if active_incident:
            cursor.execute(
                """UPDATE incidents SET evidence = %s::jsonb
                   WHERE id = %s""",
                (Json(evidence), active_incident[0]),
            )
            return
        cursor.execute(
            """INSERT INTO incidents
               (service_id, title, description, severity, source,
                probable_root_cause, impact_assessment, recommended_action, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                service_id,
                rule.title,
                f"Metric {rule.metric} increased beyond the configured threshold.",
                rule.severity,
                source,
                rule.probable_root_cause,
                rule.impact_assessment,
                rule.recommended_action,
                Json(evidence),
            ),
        )
        LOGGER.warning(
            "Metric rule %s triggered for %s (%s increased beyond %s)",
            rule.name,
            service.name,
            rule.metric,
            rule.threshold,
        )
    elif active_incident and not counter_reset:
        cursor.execute(
            """UPDATE incidents
               SET status = 'resolved', resolved_at = NOW(),
                   evidence = evidence || %s::jsonb
               WHERE id = %s""",
            (Json({"recovery": evidence}), active_incident[0]),
        )
        LOGGER.info("Resolved metric rule incident for %s (%s)", service.name, rule.name)


def _evaluate_event_rule(cursor, service_id: int, service: ServiceConfig, rule: EventRule) -> None:
    """Evaluate a rule against recently ingested, timestamped service events."""
    filter_json = Json(rule.filters)
    cursor.execute(
        """SELECT COUNT(*) FROM logs
           WHERE service_id = %s
             AND occurred_at >= NOW() - (%s * INTERVAL '1 second')
             AND metadata @> %s::jsonb""",
        (service_id, rule.lookback_seconds, filter_json),
    )
    occurrence_count = cursor.fetchone()[0]

    cursor.execute(
        """SELECT id, level, message, metadata, occurred_at, collected_at
           FROM logs
           WHERE service_id = %s
             AND occurred_at >= NOW() - (%s * INTERVAL '1 second')
             AND metadata @> %s::jsonb
           ORDER BY occurred_at DESC, id DESC
           LIMIT 20""",
        (service_id, rule.lookback_seconds, filter_json),
    )
    recent_events = [
        {
            "id": event_id,
            "level": level,
            "message": message,
            "metadata": metadata,
            "occurred_at": occurred_at.isoformat(),
            "collected_at": collected_at.isoformat(),
        }
        for event_id, level, message, metadata, occurred_at, collected_at in cursor.fetchall()
    ]

    source = f"threshold_event_{rule.name}"
    cursor.execute(
        """SELECT id FROM incidents
           WHERE service_id = %s AND source = %s
             AND status IN ('open', 'acknowledged')
           LIMIT 1""",
        (service_id, source),
    )
    active_incident = cursor.fetchone()
    evidence = {
        "rule": rule.name,
        "filters": rule.filters,
        "lookback_seconds": rule.lookback_seconds,
        "min_occurrences": rule.min_occurrences,
        "occurrence_count": occurrence_count,
        "recent_events": recent_events,
        "confidence": {
            "observed_signal": "high",
            "probable_root_cause": "low",
            "reason": (
                "Matching events were reported by the service, but the event alone does not "
                "identify the underlying cause or quantify user impact."
            ),
        },
    }

    if occurrence_count >= rule.min_occurrences:
        if active_incident:
            cursor.execute(
                "UPDATE incidents SET evidence = %s::jsonb WHERE id = %s",
                (Json(evidence), active_incident[0]),
            )
            return
        cursor.execute(
            """INSERT INTO incidents
               (service_id, title, description, severity, source,
                probable_root_cause, impact_assessment, recommended_action, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                service_id,
                rule.title,
                f"{occurrence_count} matching service event(s) were reported in the configured lookback window.",
                rule.severity,
                source,
                rule.probable_root_cause,
                rule.impact_assessment,
                rule.recommended_action,
                Json(evidence),
            ),
        )
        LOGGER.warning(
            "Event rule %s triggered for %s (%d matching events)",
            rule.name,
            service.name,
            occurrence_count,
        )
    elif active_incident:
        cursor.execute(
            """UPDATE incidents
               SET status = 'resolved', resolved_at = NOW(),
                   evidence = evidence || %s::jsonb
               WHERE id = %s""",
            (Json({"recovery": evidence}), active_incident[0]),
        )
        LOGGER.info("Resolved event rule incident for %s (%s)", service.name, rule.name)


def _evaluate_log_rule(cursor, service_id: int, service: ServiceConfig, rule: LogRule) -> None:
    """Open or resolve an incident from repeated matching logs in a time window."""
    match_clause = ""
    parameters: list[object] = [service_id, rule.lookback_seconds, list(rule.levels)]
    if rule.message_contains is not None:
        match_clause = "AND POSITION(LOWER(%s) IN LOWER(message)) > 0"
        parameters.append(rule.message_contains)

    where_clause = f"""service_id = %s
           AND occurred_at >= NOW() - (%s * INTERVAL '1 second')
           AND level = ANY(%s)
           {match_clause}"""
    cursor.execute(f"SELECT COUNT(*) FROM logs WHERE {where_clause}", parameters)
    occurrence_count = cursor.fetchone()[0]

    cursor.execute(
        f"""SELECT id, level, message, metadata, occurred_at, collected_at
            FROM logs WHERE {where_clause}
            ORDER BY occurred_at DESC, id DESC LIMIT 20""",
        parameters,
    )
    recent_logs = [
        {
            "id": log_id,
            "level": level,
            "message": message,
            "metadata": metadata,
            "occurred_at": occurred_at.isoformat(),
            "collected_at": collected_at.isoformat(),
        }
        for log_id, level, message, metadata, occurred_at, collected_at in cursor.fetchall()
    ]

    source = f"threshold_log_{rule.name}"
    cursor.execute(
        """SELECT id FROM incidents
           WHERE service_id = %s AND source = %s
             AND status IN ('open', 'acknowledged')
           LIMIT 1""",
        (service_id, source),
    )
    active_incident = cursor.fetchone()
    evidence = {
        "rule": rule.name,
        "levels": list(rule.levels),
        "message_contains": rule.message_contains,
        "lookback_seconds": rule.lookback_seconds,
        "min_occurrences": rule.min_occurrences,
        "occurrence_count": occurrence_count,
        "recent_logs": recent_logs,
        "confidence": {
            "observed_signal": "high",
            "probable_root_cause": "low",
            "reason": (
                "The matching error-level log entries are directly observed, but their count and text "
                "alone do not prove the underlying cause or user impact."
            ),
        },
    }

    if occurrence_count >= rule.min_occurrences:
        if active_incident:
            cursor.execute(
                "UPDATE incidents SET evidence = %s::jsonb WHERE id = %s",
                (Json(evidence), active_incident[0]),
            )
            return
        cursor.execute(
            """INSERT INTO incidents
               (service_id, title, description, severity, source,
                probable_root_cause, impact_assessment, recommended_action, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                service_id,
                rule.title,
                f"{occurrence_count} matching log record(s) occurred within the configured lookback window.",
                rule.severity,
                source,
                rule.probable_root_cause,
                rule.impact_assessment,
                rule.recommended_action,
                Json(evidence),
            ),
        )
        LOGGER.warning(
            "Log rule %s triggered for %s (%d matching records)",
            rule.name,
            service.name,
            occurrence_count,
        )
    elif active_incident:
        cursor.execute(
            """UPDATE incidents
               SET status = 'resolved', resolved_at = NOW(),
                   evidence = evidence || %s::jsonb
               WHERE id = %s""",
            (Json({"recovery": evidence}), active_incident[0]),
        )
        LOGGER.info("Resolved log rule incident for %s (%s)", service.name, rule.name)


def poll_service(connection, service: ServiceConfig, event_cursors: dict[str, datetime]) -> None:
    """Poll one service; failures are logged while other services continue."""
    with connection:
        with connection.cursor() as cursor:
            service_id = _upsert_service(cursor, service)

            health_ok = False
            health_status: str | None = None
            health_error: str | None = None
            try:
                health = _fetch_json(service.base_url + service.endpoints["health"])
                if isinstance(health, dict):
                    health_status = str(health.get("status", "")) or None
                health_ok = isinstance(health, dict) and str(health.get("status", "")).lower() in {"ok", "healthy"}
                if not health_ok:
                    health_error = "Health response status was not 'ok' or 'healthy'."
            except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
                health_error = str(exc)
                LOGGER.warning("Health scrape failed for %s: %s", service.name, exc)
            if health_ok:
                cursor.execute(
                    "UPDATE services SET status = 'healthy', last_seen_at = NOW() WHERE id = %s",
                    (service_id,),
                )
            else:
                cursor.execute("UPDATE services SET status = 'unhealthy' WHERE id = %s", (service_id,))

            scrape_ok = False
            scrape_error: str | None = None
            samples: list[Sample] = []
            try:
                body, _ = _get(service.base_url + service.endpoints["metrics"], "text/plain; version=0.0.4")
                samples = parse_prometheus_text(body.decode("utf-8"))
                scrape_ok = True
            except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, ValueError, OSError) as exc:
                scrape_error = str(exc)
                LOGGER.warning("Metrics scrape failed for %s: %s", service.name, exc)
            _store_metrics(cursor, service_id, service, samples, scrape_ok)
            if health_ok and scrape_ok:
                _resolve_availability_incident(cursor, service_id, service)
            else:
                _open_availability_incident(
                    cursor, service_id, service, health_ok, health_status, health_error,
                    scrape_ok, scrape_error,
                )
            if scrape_ok:
                for rule in service.metric_rules:
                    _evaluate_metric_rule(cursor, service_id, service, rule)
            for rule in service.log_rules:
                _evaluate_log_rule(cursor, service_id, service, rule)

            if "events" in service.endpoints:
                initial_event_lookback = max(
                    (rule.lookback_seconds for rule in service.event_rules),
                    default=0,
                )
                since = event_cursors.get(
                    service.name,
                    datetime.now(timezone.utc) - timedelta(seconds=initial_event_lookback),
                )
                query = urlencode({"since": since.isoformat().replace("+00:00", "Z")})
                try:
                    events = _fetch_json(
                        service.base_url + service.endpoints["events"] + "?" + query
                    )
                    _store_events(cursor, service_id, service, events)
                    event_cursors[service.name] = datetime.now(timezone.utc)
                    for rule in service.event_rules:
                        _evaluate_event_rule(cursor, service_id, service, rule)
                except HTTPError as exc:
                    if exc.code != 404:
                        LOGGER.warning("Events scrape failed for %s: %s", service.name, exc)
                except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                    LOGGER.warning("Events scrape failed for %s: %s", service.name, exc)


def run() -> None:
    registry_path = os.getenv("REGISTRY_PATH", "/app/registry/services.yaml")
    database_url = os.environ["DATABASE_URL"]
    services = load_registry(registry_path)
    event_cursors: dict[str, datetime] = {}
    next_poll = {service.name: 0.0 for service in services}
    LOGGER.info("Loaded %d registered services", len(services))

    while True:
        now = time.monotonic()
        due = [service for service in services if next_poll[service.name] <= now]
        if not due:
            time.sleep(max(0.1, min(next_poll[s.name] for s in services) - now))
            continue
        for service in due:
            connection = None
            try:
                connection = psycopg2.connect(database_url)
                poll_service(connection, service, event_cursors)
            except psycopg2.Error:
                LOGGER.exception("Database operation failed while collecting %s", service.name)
            finally:
                if connection is not None:
                    connection.close()
            next_poll[service.name] = time.monotonic() + service.scrape_interval_seconds


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run()
