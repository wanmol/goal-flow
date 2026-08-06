"""
Observability：agent_kit 内统一的 metric / trace 抽象接入点。

设计原则：
- agent_kit 包不直接绑定 Langfuse / Prometheus / 任何具体 trace/metric 后端
- 通过抽象接口让调用方注入实现（业务侧把 emit_counter / Langfuse 接进来）
- 不可用时**全部降级为 noop**，业务永远不会因为埋点失败而挂
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable, Optional

from agent_kit.harness.settings import HARNESS_SETTINGS

logger = logging.getLogger(__name__)

CounterEmitter = Callable[..., None]
HistogramEmitter = Callable[..., None]


def _noop(*args, **kwargs) -> None:  # pragma: no cover
    return None


class SpanContext:
    """``HARNESS_OBS.span(...)`` 返回的 context 对象。"""

    def __init__(self, *, span_name: str, session_id: str, callbacks: list) -> None:
        self.span_name = span_name
        self.session_id = session_id
        self.callbacks = callbacks


class Observability:
    """跨 Runtime 共享的 metric / trace 接入点。

    全局单例 ``HARNESS_OBS``。
    """

    def __init__(self) -> None:
        self._counter: CounterEmitter = _noop
        self._histogram: HistogramEmitter = _noop
        self._langfuse_enabled: bool = False
        self._langfuse_client = None

    def set_counter_emitter(self, emitter: CounterEmitter) -> None:
        """注入 counter 实现（业务侧的 emit_counter）。"""
        self._counter = emitter
        logger.info(f"Observability: counter emitter registered ({emitter!r})")

    def set_histogram_emitter(self, emitter: HistogramEmitter) -> None:
        """注入 histogram 实现（业务侧的 emit_histogram）。"""
        self._histogram = emitter
        logger.info(f"Observability: histogram emitter registered ({emitter!r})")

    def enable_langfuse(self, force: bool = False) -> bool:
        """启用 Langfuse trace。自动检测 langfuse 是否可 import + 是否可建 client。"""
        if not force and not HARNESS_SETTINGS.observability.langfuse_enabled:
            logger.info("Observability: Langfuse disabled by HARNESS_SETTINGS")
            self._langfuse_enabled = False
            return False
        try:
            from langfuse import get_client

            self._langfuse_client = get_client()
            self._langfuse_enabled = True
            logger.info("Observability: Langfuse enabled")
            return True
        except Exception as e:
            logger.warning(f"Observability: Langfuse disabled (setup failed: {e})")
            self._langfuse_enabled = False
            return False

    def disable_langfuse(self) -> None:
        self._langfuse_enabled = False
        self._langfuse_client = None

    def counter(self, metric_name: str, **labels) -> None:
        """打 counter。Emitter 未注入时 noop；emitter 异常被吞掉。"""
        try:
            self._counter(metric_name, **labels)
        except Exception as e:
            logger.warning(f"Observability.counter({metric_name!r}) failed: {e}")

    def histogram(self, metric_name: str, value: float, **labels) -> None:
        """打 histogram。Emitter 未注入时 noop；emitter 异常被吞掉。"""
        try:
            self._histogram(metric_name, value=value, **labels)
        except Exception as e:
            logger.warning(f"Observability.histogram({metric_name!r}) failed: {e}")

    @contextmanager
    def span(self, span_name: str, *, session_id: str, metadata: Optional[dict] = None):
        """trace span context manager。

        metadata: 通过 langfuse propagate_attributes 注入，自动套用到所有 child
        observation（包含 LangChain CallbackHandler 创建的 TOOL / GENERATION），
        方便 UI 按业务维度过滤。
        """
        callbacks: list = []
        propagate_cm = None
        observation_cm = None

        if self._langfuse_enabled and self._langfuse_client is not None:
            try:
                from langfuse import propagate_attributes
                from langfuse.langchain import CallbackHandler

                propagate_kwargs: dict = {"session_id": session_id}
                if metadata:
                    propagate_kwargs["metadata"] = metadata
                propagate_cm = propagate_attributes(**propagate_kwargs)
                observation_cm = self._langfuse_client.start_as_current_observation(
                    as_type="span", name=span_name
                )
                callbacks.append(CallbackHandler())
            except Exception as e:
                logger.warning(
                    f"Observability.span({span_name!r}): Langfuse setup failed: {e}"
                )
                propagate_cm = None
                observation_cm = None

        ctx = SpanContext(span_name=span_name, session_id=session_id, callbacks=callbacks)

        if propagate_cm is not None and observation_cm is not None:
            with propagate_cm:
                with observation_cm:
                    yield ctx
        else:
            yield ctx

    def reset(self) -> None:
        """全部恢复 noop 状态。仅单测使用。"""
        self._counter = _noop
        self._histogram = _noop
        self._langfuse_enabled = False
        self._langfuse_client = None


HARNESS_OBS = Observability()
