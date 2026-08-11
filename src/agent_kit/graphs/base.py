"""GraphBuilder: the strategy interface for constructing a concrete LangGraph instance.

Design intent: decouple the "assembling calls to the underlying graph construction API" from the
Runtime subclass inheritance hierarchy, turning it into a strategy object. The ``Agent`` class
holds a ``GraphBuilder`` instance and calls ``build(...)`` to obtain a ``CompiledGraph``.

3 built-in implementations:
- ``ReactGraphBuilder`` ← ``langchain.agents.create_agent``
- ``DeepGraphBuilder`` ← ``deepagents.create_deep_agent``
- ``CustomGraphBuilder`` ← user-provided callable

Business code can implement its own ``GraphBuilder`` (e.g. hand-assembling a StateGraph on langgraph).
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from langchain.agents.middleware import AgentMiddleware


@runtime_checkable
class GraphBuilder(Protocol):
    """Strategy for constructing a CompiledGraph.

    Implementations require ``build(**kwargs) -> CompiledGraph``, with the parameter naming convention:

    - ``model``: a ``BaseChatModel`` instance
    - ``tools``: ``Sequence[BaseTool]``
    - ``middleware``: ``Sequence[AgentMiddleware]``
    - ``output_schema``: ``Optional[type[BaseModel]]``
    - ``**extra``: strategy-specific parameters (e.g. deepagents' subagents / memory)

    The returned ``CompiledGraph`` must have an ``.invoke(input, config=...)`` method.
    """

    def build(
        self,
        *,
        model: Any,
        tools: Sequence[Any] = (),
        middleware: Sequence[AgentMiddleware] = (),
        output_schema: Optional[type] = None,
        **extra: Any,
    ) -> Any: ...
