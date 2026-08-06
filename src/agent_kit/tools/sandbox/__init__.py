"""沙盒代码执行：抽象执行器 + Dify 默认实现 + LangChain Tool 工厂。

``make_sandbox_tool()`` 返回的 ``BaseTool`` 可直接进 ``Agent(tools=[...])``；
``DifySandboxExecutor`` 为默认实现，业务可继承 ``BaseSandboxExecutor`` 替换。
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
