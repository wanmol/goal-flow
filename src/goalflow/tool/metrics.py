"""
结构化 metric 工具：统一 metric 埋点接口，便于 Prometheus / Grafana 接入。

设计目标：
1. **零侵入**：metric 失败永不影响业务流程（所有调用包在 try/except 里）
2. **日志双通道**：同时写到结构化 logger（便于 grep）和 Prometheus（便于看板）
3. **延迟加载**：prometheus_client 未安装时仅写日志，不报错（dev 环境无依赖）

用法：
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

# 延迟加载 prometheus_client；未安装也不报错
try:
    from prometheus_client import Counter as _PromCounter, Histogram as _PromHistogram
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    _PromCounter = None  # type: ignore[assignment]
    _PromHistogram = None  # type: ignore[assignment]

# Prometheus client 要求每个 metric 的 label 名一致；这里按 name 缓存实例
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
    """计数 metric。labels 可任意字段名。

    始终写一条 INFO 日志（``[metric] name=... value=... labels=...``），
    Prometheus 不可用时仅写日志不抛错。
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
    """直方图 metric（用于延迟、计数分布等）。"""
    label_keys = sorted(labels.keys())
    label_values = {k: str(labels[k]) for k in label_keys}
    try:
        h = _get_or_create_histogram(name, label_keys)
        if h is not None:
            (h.labels(**label_values) if label_values else h).observe(value)
    except Exception as e:
        _logger.warning(f"[metric] histogram emit failed name={name} err={e}")
    _logger.info(f"[metric] {name} value={value} {label_values}")
