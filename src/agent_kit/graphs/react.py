"""ReactGraphBuilder: a strategy wrapper around ``langchain.agents.create_agent``.

Purpose: the most common tool-calling Agent. Covers classification / extraction / rewriting / simple QA scenarios.

Constructor arguments:
- ``response_format``: optional structured response (synonymous with ``create_agent``'s ``response_format``)
- ``checkpointer``: optional custom checkpointer; defaults to ``InMemorySaver``
- ``**extra``: passed through to ``create_agent``
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


class ReactGraphBuilder:
    """A GraphBuilder based on ``langchain.agents.create_agent``."""

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
        # response_format / output_schema: constructor argument takes priority; then what the Agent passes in
        rf = self._response_format or output_schema
        if rf is not None:
            kwargs["response_format"] = rf
        if self._context_schema is not None:
            kwargs["context_schema"] = self._context_schema

        kwargs.update(self._extra)
        kwargs.update(extra)

        return create_agent(**kwargs)
