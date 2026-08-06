"""MetricsMiddleware：用 ``wrap_model_call`` 自动埋点延迟/计数。

设计意图：替代 ``AgentRuntime.run()`` 状态机里手写的 emit_counter / emit_histogram
散点埋点。本中间件统一在 model 调用边界打：

- ``<prefix>.model_call_latency_ms`` (histogram, outcome=ok|error)
- ``<prefix>.model_failed`` (counter, error_class=..., error_kind=...)

依赖 ``Harness.tracer`` 的 ``counter()`` / ``histogram()`` 方法。
Tracer 未配置 emitter 时降级为 noop。
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)


def _classify_error(error: BaseException) -> str:
    """把异常归到 metric label：compliance / tool_json / network / other。

    与 ``agent_kit.runtimes.base.classify_error`` 同语义；为了避免循环依赖，
    本模块独立实现。
    """
    text = str(error).lower()
    if not text:
        return "other"
    if any(
        k in text
        for k in (
            "inappropriate", "policy", "violat", "datainspectionfailed",
            "内容违规", "合规", "敏感",
        )
    ):
        return "compliance"
    if "function.arguments" in text or "json" in text or (
        "tool" in text and "arguments" in text
    ):
        return "tool_json"
    if "timeout" in text or "connection" in text or "network" in text or "refused" in text:
        return "network"
    return "other"


class MetricsMiddleware(AgentMiddleware[ContextAgentState, ContextT, ResponseT]):
    """围绕 model 调用自动埋点。

    构造参数：
    - ``harness``：``Harness`` 实例，从中读 ``tracer``
    - ``prefix``：metric 命名空间前缀，默认 ``"agent"``。最终 metric 名形如
      ``<prefix>.model_call_latency_ms`` / ``<prefix>.model_failed``
    """

    def __init__(self, harness: object, *, prefix: str = "agent"):
        self._harness = harness
        self._prefix = prefix.rstrip(".")

    def _tracer(self):
        return getattr(self._harness, "tracer", None)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        tracer = self._tracer()
        t0 = time.perf_counter()
        try:
            response = handler(request)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            err_kind = _classify_error(e)
            try:
                if tracer is not None:
                    tracer.histogram(
                        f"{self._prefix}.model_call_latency_ms",
                        value=elapsed_ms,
                        outcome="error",
                    )
                    tracer.counter(
                        f"{self._prefix}.model_failed",
                        error_class=type(e).__name__,
                        error_kind=err_kind,
                    )
            except Exception as emit_err:
                logger.warning(
                    f"MetricsMiddleware: failed to emit metrics: {emit_err}"
                )
            raise

        elapsed_ms = (time.perf_counter() - t0) * 1000
        try:
            if tracer is not None:
                tracer.histogram(
                    f"{self._prefix}.model_call_latency_ms",
                    value=elapsed_ms,
                    outcome="ok",
                )
        except Exception as emit_err:
            logger.warning(
                f"MetricsMiddleware: failed to emit ok latency: {emit_err}"
            )
        return response
