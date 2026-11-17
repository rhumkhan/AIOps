"""Small parser for Prometheus text exposition samples."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAMPLE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+'
    r'(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]?(?:Inf|NaN))'
    r'(?:\s+\d+)?\s*$'
)
_LABEL = re.compile(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"\s*')


@dataclass(frozen=True)
class Sample:
    name: str
    value: float
    labels: dict[str, str]


def _parse_labels(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    position = 0
    while position < len(text):
        match = _LABEL.match(text, position)
        if not match:
            raise ValueError(f"Invalid Prometheus label set near {text[position:]!r}")
        key, raw_value = match.groups()
        if key in labels:
            raise ValueError(f"Duplicate Prometheus label: {key}")
        labels[key] = re.sub(r'\\([\\"n])', lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), raw_value)
        position = match.end()
        if position < len(text):
            if text[position] != ",":
                raise ValueError(f"Expected ',' in Prometheus labels near {text[position:]!r}")
            position += 1
    return labels


def parse_prometheus_text(payload: str) -> list[Sample]:
    """Return numeric samples; malformed non-comment lines are skipped."""
    samples: list[Sample] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE.match(line)
        if not match:
            continue
        try:
            labels = _parse_labels(match.group("labels") or "")
            samples.append(Sample(match.group("name"), float(match.group("value")), labels))
        except ValueError as exc:
            raise ValueError(f"Invalid sample on line {line_number}: {exc}") from exc
    return samples
