"""MetricsMiddleware: automatically instrument latency/counts via ``wrap_model_call``.

Design intent: replaces the hand-written, scattered emit_counter / emit_histogram instrumentation
in the ``AgentRuntime.run()`` state machine. This middleware instruments uniformly at the model call boundary:

- ``<prefix>.model_call_latency_ms`` (histogram, outcome=ok|error)
- ``<prefix>.model_failed`` (counter, error_class=..., error_kind=...)

Depends on the ``counter()`` / ``histogram()`` methods of ``Harness.tracer``.
Degrades to noop when the Tracer has no emitter configured.
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
    """Classify the exception into a metric label: compliance / tool_json / network / other.

    Same semantics as ``agent_kit.runtimes.base.classify_error``; implemented independently in
    this module to avoid a circular dependency.
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
    """Automatically instrument around the model call.

    Constructor parameters:
    - ``harness``: the ``Harness`` instance, from which ``tracer`` is read
    - ``prefix``: metric namespace prefix, default ``"agent"``. Final metric names look like
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
