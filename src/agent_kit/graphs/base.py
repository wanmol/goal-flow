"""GraphBuilder：构造具体 LangGraph 实例的策略接口。

设计意图：把"调底层 graph 构造 API 拼图"从 Runtime 子类继承结构里解耦，做成
策略对象。``Agent`` 类持有一个 ``GraphBuilder`` 实例，调用 ``build(...)`` 拿
``CompiledGraph``。

3 个内置实现：
- ``ReactGraphBuilder`` ← ``langchain.agents.create_agent``
- ``DeepGraphBuilder`` ← ``deepagents.create_deep_agent``
- ``CustomGraphBuilder`` ← 用户提供 callable

业务可以实现自己的 ``GraphBuilder``（如基于 langgraph 手拼 StateGraph）。
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from langchain.agents.middleware import AgentMiddleware


@runtime_checkable
class GraphBuilder(Protocol):
    """构造 CompiledGraph 的策略。

    实现要求 ``build(**kwargs) -> CompiledGraph``，参数名约定如下：

    - ``model``：``BaseChatModel`` 实例
    - ``tools``：``Sequence[BaseTool]``
    - ``middleware``：``Sequence[AgentMiddleware]``
    - ``output_schema``：``Optional[type[BaseModel]]``
    - ``**extra``：策略特有参数（如 deepagents 的 subagents / memory）

    返回的 ``CompiledGraph`` 必须有 ``.invoke(input, config=...)`` 方法。
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
