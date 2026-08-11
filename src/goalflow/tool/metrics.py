"""
Structured metric utility: a unified metric instrumentation interface, for easy integration with Prometheus / Grafana.

Design goals:
1. **Zero intrusion**: metric failures never affect the business flow (all calls wrapped in try/except)
2. **Dual log channel**: writes to both the structured logger (easy to grep) and Prometheus (easy dashboards)
3. **Lazy loading**: when prometheus_client is not installed, only writes logs without erroring (no dependency in dev environments)

Usage:
    from goalflow.tool.metrics import emit_counter, emit_histogram

    emit_counter("requirement_collection.find_best_leaf_fallback",
                 trigger="non_leaf_top1_after_drill",
                 category_id="123")

    emit_histogram("requirement_collection.web_search_latency_ms",
                   value=1234.5,
                   query_type="essentials")
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger("metrics")

# Lazily load prometheus_client; no error even if not installed
try:
    from prometheus_client import Counter as _PromCounter, Histogram as _PromHistogram
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    _PromCounter = None  # type: ignore[assignment]
    _PromHistogram = None  # type: ignore[assignment]

# Prometheus client requires each metric to have consistent label names; cache instances by name here
_counters: dict[str, Any] = {}
_histograms: dict[str, Any] = {}


def _get_or_create_counter(name: str, label_keys: list[str]) -> Any | None:
    if not _PROM_AVAILABLE:
        return None
    if name not in _counters:
        try:
            _counters[name] = _PromCounter(name.replace(".", "_"), name, label_keys)
        except Exception as e:
            _logger.warning(f"[metric] failed to create counter {name}: {e}")
            _counters[name] = None
    return _counters[name]


def _get_or_create_histogram(name: str, label_keys: list[str]) -> Any | None:
    if not _PROM_AVAILABLE:
        return None
    if name not in _histograms:
        try:
            _histograms[name] = _PromHistogram(name.replace(".", "_"), name, label_keys)
        except Exception as e:
            _logger.warning(f"[metric] failed to create histogram {name}: {e}")
            _histograms[name] = None
    return _histograms[name]


def emit_counter(name: str, value: int = 1, **labels: Any) -> None:
    """Counter metric. labels can use any field names.

    Always writes an INFO log (``[metric] name=... value=... labels=...``);
    when Prometheus is unavailable, only writes logs without raising.
    """
    label_keys = sorted(labels.keys())
    label_values = {k: str(labels[k]) for k in label_keys}
    try:
        c = _get_or_create_counter(name, label_keys)
        if c is not None:
            (c.labels(**label_values) if label_values else c).inc(value)
    except Exception as e:
        _logger.warning(f"[metric] counter emit failed name={name} err={e}")
    _logger.info(f"[metric] {name} value={value} {label_values}")


def emit_histogram(name: str, value: float, **labels: Any) -> None:
    """Histogram metric (used for latency, count distributions, etc.)."""
    label_keys = sorted(labels.keys())
    label_values = {k: str(labels[k]) for k in label_keys}
    try:
        h = _get_or_create_histogram(name, label_keys)
        if h is not None:
            (h.labels(**label_values) if label_values else h).observe(value)
    except Exception as e:
        _logger.warning(f"[metric] histogram emit failed name={name} err={e}")
    _logger.info(f"[metric] {name} value={value} {label_values}")
