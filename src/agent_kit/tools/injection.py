"""Convenience injection helpers for Tools.

Design intent: replaces the old approach of ``AgentRuntime.make_tool`` injecting result via ContextVar.
Business code is recommended to use LangChain's native ``InjectedState`` / ``InjectedToolArg``:

    from typing import Annotated
    from langchain_core.tools import tool, InjectedToolArg
    from langgraph.prebuilt import InjectedState

    @tool
    def my_tool(
        n: int,
        state: Annotated[dict, InjectedState],
    ) -> str:
        '''Add n to state['agent_output'].counter.'''
        output = state.get("agent_output")
        output.counter += n
        return f"counter={output.counter}"

This module provides a semantic alias to simplify the common pattern.
"""
from __future__ import annotations

from typing import Annotated, Any

# Direct re-export, so business code can import from here without caring which underlying package it comes from
from langgraph.prebuilt import InjectedState


def InjectedAgentOutput() -> Any:
    """Convenience helper: a semantic alias for ``Annotated[Any, InjectedState]``, emphasizing
    the common pattern of "injecting ``agent_output`` from state".

    Usage::

        @tool
        def my_tool(
            n: int,
            state: Annotated[dict, InjectedAgentOutput()],
        ) -> str:
            output = state.get("agent_output")
            output.counter += n
            return f"counter={output.counter}"

    Returns the LangChain ``InjectedState`` marker, fully equivalent to the native ``Annotated[dict, InjectedState]``;
    the alias just makes the intent clearer.
    """
    return InjectedState


__all__ = ["InjectedState", "InjectedAgentOutput"]
