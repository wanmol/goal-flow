"""Sandbox code execution: abstract executor + Dify default implementation + LangChain Tool factory.

The ``BaseTool`` returned by ``make_sandbox_tool()`` can go directly into ``Agent(tools=[...])``;
``DifySandboxExecutor`` is the default implementation, and business code can subclass ``BaseSandboxExecutor`` to replace it.
"""
from agent_kit.tools.sandbox.executor import (
    BaseSandboxExecutor,
    DifySandboxExecutor,
    check_code,
)
from agent_kit.tools.sandbox.tool import make_sandbox_tool

__all__ = [
    "BaseSandboxExecutor",
    "DifySandboxExecutor",
    "make_sandbox_tool",
    "check_code",
]
