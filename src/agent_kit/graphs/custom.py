"""CustomGraphBuilder：用户自定义 graph 构造策略。

定位：业务需要完全自定义状态机（手拼 ``StateGraph``、议价 Tit-for-Tat、复核流水线
等）时使用。把构造函数当作 callable 注入。

构造参数：
- ``builder_fn``：``Callable[..., CompiledGraph]``，签名约定与 ``GraphBuilder.build`` 一致
  （接 ``model`` / ``tools`` / ``middleware`` / ``output_schema`` / ``**extra``）
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from langchain.agents.middleware import AgentMiddleware


BuilderFn = Callable[..., Any]


class CustomGraphBuilder:
    """用户传 callable 的 GraphBuilder。

    用法::

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
