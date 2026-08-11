"""CustomGraphBuilder: a user-defined graph construction strategy.

Purpose: use it when business code needs a fully custom state machine (hand-assembled ``StateGraph``,
Tit-for-Tat negotiation, review pipelines, etc.). The construction function is injected as a callable.

Constructor arguments:
- ``builder_fn``: ``Callable[..., CompiledGraph]``, with a signature matching ``GraphBuilder.build``
  (accepts ``model`` / ``tools`` / ``middleware`` / ``output_schema`` / ``**extra``)
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


BuilderFn = Callable[..., Any]


class CustomGraphBuilder:
    """A GraphBuilder that takes a user-supplied callable.

    Usage::

        def my_builder(*, model, tools, middleware, output_schema=None, **kw):
            g = StateGraph(MyState)
            g.add_node("decide", lambda s: ...)
            g.add_node("act", lambda s: ...)
            g.set_entry_point("decide")
            return g.compile(checkpointer=InMemorySaver())

        agent = Agent(graph_builder=CustomGraphBuilder(my_builder), ...)
    """

    def __init__(self, builder_fn: BuilderFn):
        self._builder_fn = builder_fn

    def build(
        self,
        *,
        model: Any,
        tools: Sequence[Any] = (),
        middleware: Sequence[AgentMiddleware] = (),
        output_schema: Optional[type] = None,
        **extra: Any,
    ) -> Any:
        return self._builder_fn(
            model=model,
            tools=list(tools),
            middleware=list(middleware),
            output_schema=output_schema,
            **extra,
        )
