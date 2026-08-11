"""LangfuseTracingMiddleware: wraps ``harness.tracer.span`` as an agent-boundary span.

Design intent: replaces the hand-written ``with HARNESS_OBS.span(...):`` context management in
``AgentRuntime._stream_agent_messages``. Turns "opening a span around the agent lifecycle"
into a pluggable middleware.

Behavior:
- ``before_agent`` opens the span (writes to state["__langfuse_span"], so after_agent can close it)
- ``after_agent`` closes the span
- Degrades to noop when Langfuse is unavailable / harness.tracer does not exist
"""
from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing_extensions import override

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)

_SPAN_STATE_KEY = "__langfuse_span_cm__"


class LangfuseTracingMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """Open / close a Langfuse span around the agent lifecycle.

    Constructor parameters:
    - ``harness``: the ``Harness`` instance, from which the ``span()`` context manager is read via ``tracer``
    - ``span_prefix``: span name prefix, default ``"agent"``. Final ``<prefix>_run``
    - ``session_id_field``: which field of ``runtime.context`` to read session_id from;
      default ``"sys_conversation_id"``
    """

    def __init__(
        self,
        harness: object,
        *,
        span_prefix: str = "agent",
        session_id_field: str = "sys_conversation_id",
    ):
        self._harness = harness
        self._span_prefix = span_prefix.rstrip("_")
        self._session_id_field = session_id_field

    def _tracer(self):
        return getattr(self._harness, "tracer", None)

    def _resolve_session_id(self, runtime: "Runtime[ContextT]") -> str:
        ctx = getattr(runtime, "context", None)
        if ctx is None:
            return "default"
        value = getattr(ctx, self._session_id_field, None)
        if value is None and hasattr(ctx, "get"):
            value = ctx.get(self._session_id_field)
        return str(value) if value else "default"

    @override
    def before_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        tracer = self._tracer()
        if tracer is None:
            return None
        try:
            cm = tracer.span(
                f"{self._span_prefix}_run",
                session_id=self._resolve_session_id(runtime),
                metadata={"span_prefix": self._span_prefix},
            )
            cm.__enter__()
        except Exception as e:
            logger.warning(f"LangfuseTracingMiddleware: span enter failed: {e}")
            return None
        # Stash the context manager into state; after_agent pulls it out to close
        return {_SPAN_STATE_KEY: cm}

    @override
    def after_agent(
        self, state: ContextAgentState, runtime: "Runtime[ContextT]"
    ) -> dict[str, Any] | None:
        cm = state.get(_SPAN_STATE_KEY) if isinstance(state, dict) else None
        if cm is None:
            return None
        try:
            cm.__exit__(None, None, None)
        except Exception as e:
            logger.warning(f"LangfuseTracingMiddleware: span exit failed: {e}")
        # Clean up the state key
        return {_SPAN_STATE_KEY: None}
