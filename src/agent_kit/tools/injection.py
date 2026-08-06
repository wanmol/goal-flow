"""Tool 工具的便利注入助手。

设计意图：替代 ``AgentRuntime.make_tool`` 用 ContextVar 注入 result 的老做法。
推荐业务用 LangChain 原生 ``InjectedState`` / ``InjectedToolArg``：

    from typing import Annotated
    from langchain_core.tools import tool, InjectedToolArg
    from langgraph.prebuilt import InjectedState

    @tool
    def my_tool(
        n: int,
        state: Annotated[dict, InjectedState],
    ) -> str:
        '''加 n 到 state['agent_output'].counter.'''
        output = state.get("agent_output")
        output.counter += n
        return f"counter={output.counter}"

本模块提供一个语义化的别名简化常见模式。
"""
from __future__ import annotations

from typing import Annotated, Any

# 直接 re-export，业务可以从这里 import 而无需关心底层来自哪个包
from langgraph.prebuilt import InjectedState


def InjectedAgentOutput() -> Any:
    """便利助手：``Annotated[Any, InjectedState]`` 的语义化别名，强调
    "从 state 注入 ``agent_output``" 这一常见模式。

    用法::

        @tool
        def my_tool(
            n: int,
            state: Annotated[dict, InjectedAgentOutput()],
        ) -> str:
            output = state.get("agent_output")
            output.counter += n
            return f"counter={output.counter}"

    返回的是 LangChain ``InjectedState`` 标记，与原生 ``Annotated[dict, InjectedState]``
    完全等价；只是别名更显意图。
    """
    return InjectedState


__all__ = ["InjectedState", "InjectedAgentOutput"]
