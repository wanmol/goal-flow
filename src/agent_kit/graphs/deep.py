"""DeepGraphBuilder: a strategy wrapper around ``deepagents.create_deep_agent``.

Purpose: multi-step requirement gathering / planning / subagents / todos scenarios.

Constructor arguments:
- ``subagents``: list of sub-agents
- ``memory``: list of AGENTS.md paths loaded into the prompt at startup
- ``interrupt_on``: HITL interrupt-tool config ``dict[tool_name, InterruptOnConfig | bool]``
- ``response_format``: structured response
- ``checkpointer``: defaults to ``InMemorySaver``
- ``**extra``: passed through
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


class DeepGraphBuilder:
    """A GraphBuilder based on ``deepagents.create_deep_agent``."""

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
