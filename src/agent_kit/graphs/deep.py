"""DeepGraphBuilder：``deepagents.create_deep_agent`` 的策略包装。

定位：多步骤需求收集 / planning / subagents / todos 场景。

构造参数：
- ``subagents``：sub-agent 列表
- ``memory``：启动加载到 prompt 的 AGENTS.md 路径列表
- ``interrupt_on``：HITL 中断工具配置 ``dict[tool_name, InterruptOnConfig | bool]``
- ``response_format``：结构化响应
- ``checkpointer``：默认 ``InMemorySaver``
- ``**extra``：透传
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


class DeepGraphBuilder:
    """基于 ``deepagents.create_deep_agent`` 的 GraphBuilder。"""

    def __init__(
        self,
        *,
        subagents: Optional[list] = None,
        memory: Optional[list[str]] = None,
        interrupt_on: Optional[dict] = None,
        response_format: Optional[Any] = None,
        checkpointer: Optional[Any] = None,
        context_schema: Optional[type] = None,
        **extra: Any,
    ):
        self._subagents = subagents or []
        self._memory = memory or []
        self._interrupt_on = interrupt_on or {}
        self._response_format = response_format
        self._checkpointer = checkpointer
        self._context_schema = context_schema
        self._extra = extra

    def build(
        self,
        *,
        model: Any,
        tools: Sequence[Any] = (),
        middleware: Sequence[AgentMiddleware] = (),
        output_schema: Optional[type] = None,
        **extra: Any,
    ) -> Any:
        from deepagents import create_deep_agent
        from langgraph.checkpoint.memory import InMemorySaver

        kwargs: dict = {
            "model": model,
            "tools": list(tools),
            "middleware": list(middleware),
            "checkpointer": self._checkpointer or InMemorySaver(),
        }
        if self._subagents:
            kwargs["subagents"] = self._subagents
        if self._memory:
            kwargs["memory"] = self._memory
        if self._interrupt_on:
            kwargs["interrupt_on"] = self._interrupt_on
        rf = self._response_format or output_schema
        if rf is not None:
            kwargs["response_format"] = rf
        if self._context_schema is not None:
            kwargs["context_schema"] = self._context_schema

        kwargs.update(self._extra)
        kwargs.update(extra)

        return create_deep_agent(**kwargs)
