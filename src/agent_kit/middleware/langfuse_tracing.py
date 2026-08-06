"""LangfuseTracingMiddleware：包装 ``harness.tracer.span`` 为 agent 边界 span。

设计意图：替代 ``AgentRuntime._stream_agent_messages`` 里手写的
``with HARNESS_OBS.span(...):`` 上下文管理。把"在 agent 生命周期外面开 span"
做成可插拔 middleware。

行为：
- ``before_agent`` 开 span（写入 state["__langfuse_span"]，便于 after_agent 关闭）
- ``after_agent`` 关 span
- Langfuse 不可用 / harness.tracer 不存在时降级 noop
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
    """围绕 agent 生命周期开 / 关 Langfuse span。

    构造参数：
    - ``harness``：``Harness`` 实例，从 ``tracer`` 读 ``span()`` context manager
    - ``span_prefix``：span name 前缀，默认 ``"agent"``。最终 ``<prefix>_run``
    - ``session_id_field``：从 ``runtime.context`` 哪个字段读 session_id；
      默认 ``"sys_conversation_id"``
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
        # 把 context manager 暂存到 state，after_agent 取出关闭
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
        # 清理 state key
        return {_SPAN_STATE_KEY: None}
