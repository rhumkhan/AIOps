"""Load and validate the application-agnostic service registry."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class MetricRule:
    name: str
    metric: str
    detection: str
    lookback_seconds: int
    threshold: float
    severity: str
    title: str
    probable_root_cause: str
    impact_assessment: str
    recommended_action: str


@dataclass(frozen=True)
class EventRule:
    name: str
    filters: dict[str, str]
    lookback_seconds: int
    min_occurrences: int
    severity: str
    title: str
    probable_root_cause: str
    impact_assessment: str
    recommended_action: str


@dataclass(frozen=True)
class LogRule:
    name: str
    levels: tuple[str, ...]
    lookback_seconds: int
    min_occurrences: int
    message_contains: str | None
    severity: str
    title: str
    probable_root_cause: str
    impact_assessment: str
    recommended_action: str


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    base_url: str
    scrape_interval_seconds: int
    endpoints: dict[str, str]
    metric_names: frozenset[str]
    default_labels: dict[str, str]
    metric_rules: tuple[MetricRule, ...]
    event_rules: tuple[EventRule, ...]
    log_rules: tuple[LogRule, ...]


def _resolve(value: Any) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            variable = match.group(1)
            if variable not in os.environ:
                raise ValueError(f"Registry requires environment variable {variable}")
            return os.environ[variable]

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_resolve(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item) for key, item in value.items()}
    return value


def load_registry(path: str | Path) -> list[ServiceConfig]:
    """Load services.yaml and resolve its ${ENV_VAR} references."""
    with Path(path).open(encoding="utf-8") as registry_file:
        document = yaml.safe_load(registry_file) or {}

    raw_services = document.get("services")
    if not isinstance(raw_services, list) or not raw_services:
        raise ValueError("Registry must contain a non-empty services list")

    services: list[ServiceConfig] = []
    seen_names: set[str] = set()
    for raw in raw_services:
        if not isinstance(raw, dict):
            raise ValueError("Each registry service must be a mapping")
        service = _resolve(raw)
        name = service.get("name")
        base_url = service.get("base_url", "").rstrip("/")
        interval = service.get("scrape_interval_seconds")
        endpoints = service.get("endpoints", {})
        metric_names = service.get("metric_names", [])
        default_labels = service.get("default_labels", {})
        raw_metric_rules = service.get("metric_rules", [])
        raw_event_rules = service.get("event_rules", [])
        raw_log_rules = service.get("log_rules", [])

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each service must have a non-empty name")
        if name in seen_names:
            raise ValueError(f"Duplicate service name: {name}")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError(f"Service {name} must have an HTTP(S) base_url")
        if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
            raise ValueError(f"Service {name} scrape_interval_seconds must be a positive integer")
        if not isinstance(endpoints, dict) or not isinstance(metric_names, list):
            raise ValueError(f"Service {name} has invalid endpoints or metric_names")
        if not isinstance(raw_metric_rules, list):
            raise ValueError(f"Service {name} metric_rules must be a list")
        if not isinstance(raw_event_rules, list):
            raise ValueError(f"Service {name} event_rules must be a list")
        if not isinstance(raw_log_rules, list):
            raise ValueError(f"Service {name} log_rules must be a list")
        if not isinstance(default_labels, dict) or not all(
            isinstance(key, str) and isinstance(value, (str, int, float, bool))
            for key, value in default_labels.items()
        ):
            raise ValueError(f"Service {name} default_labels must contain scalar values")

        paths = {"metrics": "/metrics", "health": "/health"}
        paths.update(endpoints)
        if not all(isinstance(value, str) and value.startswith("/") for value in paths.values()):
            raise ValueError(f"Service {name} endpoint paths must start with '/'")

        configured_metric_names = frozenset(str(metric) for metric in metric_names)
        metric_rules: list[MetricRule] = []
        seen_rule_names: set[str] = set()
        for raw_rule in raw_metric_rules:
            if not isinstance(raw_rule, dict):
                raise ValueError(f"Service {name} metric rules must be mappings")
            rule_name = raw_rule.get("name")
            metric = raw_rule.get("metric")
            detection = raw_rule.get("detection")
            lookback = raw_rule.get("lookback_seconds")
            threshold = raw_rule.get("threshold")
            severity = raw_rule.get("severity")
            text_fields = (
                "title", "probable_root_cause", "impact_assessment", "recommended_action"
            )
            if not isinstance(rule_name, str) or not rule_name.strip() or rule_name in seen_rule_names:
                raise ValueError(f"Service {name} metric rule names must be non-empty and unique")
            if not isinstance(metric, str) or metric not in configured_metric_names:
                raise ValueError(f"Service {name} metric rule {rule_name} must reference an allow-listed metric")
            if detection != "increase":
                raise ValueError(f"Service {name} metric rule {rule_name} has unsupported detection; use 'increase'")
            if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 1:
                raise ValueError(f"Service {name} metric rule {rule_name} lookback_seconds must be positive")
            if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
                raise ValueError(f"Service {name} metric rule {rule_name} threshold must be numeric")
            if severity not in {"critical", "high", "medium", "low"}:
                raise ValueError(f"Service {name} metric rule {rule_name} has invalid severity")
            if any(not isinstance(raw_rule.get(field), str) or not raw_rule[field].strip() for field in text_fields):
                raise ValueError(f"Service {name} metric rule {rule_name} requires title and incident guidance text")
            metric_rules.append(MetricRule(
                name=rule_name,
                metric=metric,
                detection=detection,
                lookback_seconds=lookback,
                threshold=float(threshold),
                severity=severity,
                title=raw_rule["title"],
                probable_root_cause=raw_rule["probable_root_cause"],
                impact_assessment=raw_rule["impact_assessment"],
                recommended_action=raw_rule["recommended_action"],
            ))
            seen_rule_names.add(rule_name)

        event_rules: list[EventRule] = []
        for raw_rule in raw_event_rules:
            if not isinstance(raw_rule, dict):
                raise ValueError(f"Service {name} event rules must be mappings")
            rule_name = raw_rule.get("name")
            filters = raw_rule.get("filters")
            lookback = raw_rule.get("lookback_seconds")
            min_occurrences = raw_rule.get("min_occurrences")
            severity = raw_rule.get("severity")
            text_fields = (
                "title", "probable_root_cause", "impact_assessment", "recommended_action"
            )
            if not isinstance(rule_name, str) or not rule_name.strip() or rule_name in seen_rule_names:
                raise ValueError(f"Service {name} event rule names must be non-empty and unique")
            if not isinstance(filters, dict) or not filters or not all(
                isinstance(key, str) and isinstance(value, str) and value
                for key, value in filters.items()
            ):
                raise ValueError(f"Service {name} event rule {rule_name} filters must be non-empty string mappings")
            if "events" not in endpoints:
                raise ValueError(f"Service {name} event rule {rule_name} requires an events endpoint")
            if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 1:
                raise ValueError(f"Service {name} event rule {rule_name} lookback_seconds must be positive")
            if not isinstance(min_occurrences, int) or isinstance(min_occurrences, bool) or min_occurrences < 1:
                raise ValueError(f"Service {name} event rule {rule_name} min_occurrences must be positive")
            if severity not in {"critical", "high", "medium", "low"}:
                raise ValueError(f"Service {name} event rule {rule_name} has invalid severity")
            if any(not isinstance(raw_rule.get(field), str) or not raw_rule[field].strip() for field in text_fields):
                raise ValueError(f"Service {name} event rule {rule_name} requires title and incident guidance text")
            event_rules.append(EventRule(
                name=rule_name,
                filters={key: value for key, value in filters.items()},
                lookback_seconds=lookback,
                min_occurrences=min_occurrences,
                severity=severity,
                title=raw_rule["title"],
                probable_root_cause=raw_rule["probable_root_cause"],
                impact_assessment=raw_rule["impact_assessment"],
                recommended_action=raw_rule["recommended_action"],
            ))
            seen_rule_names.add(rule_name)

        log_rules: list[LogRule] = []
        for raw_rule in raw_log_rules:
            if not isinstance(raw_rule, dict):
                raise ValueError(f"Service {name} log rules must be mappings")
            rule_name = raw_rule.get("name")
            levels = raw_rule.get("levels")
            lookback = raw_rule.get("lookback_seconds")
            min_occurrences = raw_rule.get("min_occurrences")
            message_contains = raw_rule.get("message_contains")
            severity = raw_rule.get("severity")
            text_fields = (
                "title", "probable_root_cause", "impact_assessment", "recommended_action"
            )
            allowed_levels = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
            if not isinstance(rule_name, str) or not rule_name.strip() or rule_name in seen_rule_names:
                raise ValueError(f"Service {name} log rule names must be non-empty and unique")
            if not isinstance(levels, list) or not levels or any(
                not isinstance(level, str) or level.upper() not in allowed_levels for level in levels
            ):
                raise ValueError(f"Service {name} log rule {rule_name} levels must be a non-empty list of valid levels")
            if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 1:
                raise ValueError(f"Service {name} log rule {rule_name} lookback_seconds must be positive")
            if not isinstance(min_occurrences, int) or isinstance(min_occurrences, bool) or min_occurrences < 1:
                raise ValueError(f"Service {name} log rule {rule_name} min_occurrences must be positive")
            if message_contains is not None and (
                not isinstance(message_contains, str) or not message_contains.strip()
            ):
                raise ValueError(f"Service {name} log rule {rule_name} message_contains must be non-empty text")
            if severity not in {"critical", "high", "medium", "low"}:
                raise ValueError(f"Service {name} log rule {rule_name} has invalid incident severity")
            if any(not isinstance(raw_rule.get(field), str) or not raw_rule[field].strip() for field in text_fields):
                raise ValueError(f"Service {name} log rule {rule_name} requires title and incident guidance text")
            log_rules.append(LogRule(
                name=rule_name,
                levels=tuple(level.upper() for level in levels),
                lookback_seconds=lookback,
                min_occurrences=min_occurrences,
                message_contains=message_contains,
                severity=severity,
                title=raw_rule["title"],
                probable_root_cause=raw_rule["probable_root_cause"],
                impact_assessment=raw_rule["impact_assessment"],
                recommended_action=raw_rule["recommended_action"],
            ))
            seen_rule_names.add(rule_name)

        services.append(ServiceConfig(
            name=name,
            base_url=base_url,
            scrape_interval_seconds=interval,
            endpoints=paths,
            metric_names=configured_metric_names,
            default_labels={str(key): str(value) for key, value in default_labels.items()},
            metric_rules=tuple(metric_rules),
            event_rules=tuple(event_rules),
            log_rules=tuple(log_rules),
        ))
        seen_names.add(name)

    return services
