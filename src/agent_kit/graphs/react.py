"""ReactGraphBuilder：``langchain.agents.create_agent`` 的策略包装。

定位：最常用的 tool-calling Agent。覆盖分类 / 提取 / 改写 / 简单 QA 等场景。

构造参数：
- ``response_format``：可选结构化响应（与 ``create_agent`` 的 ``response_format`` 同义）
- ``checkpointer``：可选自定义 checkpointer；默认 ``InMemorySaver``
- ``**extra``：透传给 ``create_agent``
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


class ReactGraphBuilder:
    """基于 ``langchain.agents.create_agent`` 的 GraphBuilder。"""

    def __init__(
        self,
        *,
        response_format: Optional[Any] = None,
        checkpointer: Optional[Any] = None,
        context_schema: Optional[type] = None,
        **extra: Any,
    ):
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
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import InMemorySaver

        kwargs: dict = {
            "model": model,
            "tools": list(tools),
            "middleware": list(middleware),
            "checkpointer": self._checkpointer or InMemorySaver(),
        }
        # response_format / output_schema：构造参数优先；其次 Agent 传入
        rf = self._response_format or output_schema
        if rf is not None:
            kwargs["response_format"] = rf
        if self._context_schema is not None:
            kwargs["context_schema"] = self._context_schema

        kwargs.update(self._extra)
        kwargs.update(extra)

        return create_agent(**kwargs)
