"""Wrap ``BaseSandboxExecutor`` as a LangChain ``BaseTool``.

Design intent: code execution is a capability the model invokes autonomously (function calling), not a cross-cutting concern, so it is wrapped as a
tool rather than middleware. The model calls it only when it decides "code must be executed to get the result".

Applicable scenarios (written into the tool description to guide the model):
- Data analysis and statistical computation (pandas / numpy)
- Numerical computation and complex formulas (loops / conditionals / multi-step)
- Format conversion (JSON parsing / data wrangling)
- Chart data generation (output data, no rendering — the sandbox forbids plotting libraries)
- Any task that requires executing code to get the result

Usage::

    from agent_kit.tools.sandbox import make_sandbox_tool

    agent = MyAgent(tools=[make_sandbox_tool()])              # default Dify sandbox
    agent = MyAgent(tools=[make_sandbox_tool(MyExecutor())])  # custom executor
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from agent_kit.tools.sandbox.executor import (
    BaseSandboxExecutor,
    DifySandboxExecutor,
)

_DEFAULT_TOOL_NAME = "run_python_code"

_DEFAULT_DESCRIPTION = (
    "在隔离沙盒中执行 Python 代码并返回 stdout。适用于：数据分析与统计计算"
    "（pandas/numpy）、数值计算与复杂公式（循环/条件/多步骤）、格式转换"
    "（JSON 解析/数据整理）、图表所需数据的生成，以及任何需要真正执行代码才能"
    "得出结果的任务。\n"
    "约束：必须用 print() 输出最终结果，否则看不到任何返回；禁止使用绘图库"
    "（matplotlib/seaborn/plotly 等），如需图表请只输出数据由上层渲染；"
    "无文件系统/网络持久化保证。"
)


def _format_result(success: bool, output: str, metadata: dict) -> str:
    """Render ``(success, output, metadata)`` as text for the model to read.

    On success, return stdout directly; on failure, include exit_code so the model can tell whether it's a "code error"
    or "service unavailable" and correct accordingly.
    """
    if success:
        return output or "[Sandbox] 代码执行成功，但没有任何 stdout 输出。请用 print() 输出结果。"
    exit_code = metadata.get("exit_code")
    return f"[Sandbox] 执行失败 (exit_code={exit_code}):\n{output}"


def make_sandbox_tool(
    executor: Optional[BaseSandboxExecutor] = None,
    *,
    name: str = _DEFAULT_TOOL_NAME,
    description: Optional[str] = None,
) -> Any:
    """Construct a LangChain ``BaseTool`` that executes Python code.

    :param executor: a ``BaseSandboxExecutor`` instance; defaults to ``DifySandboxExecutor()``
    :param name: tool name (the name exposed by LangChain function-calling), defaults to ``run_python_code``
    :param description: overrides the default description (which already includes applicable scenarios and constraints)
    :returns: a LangChain ``BaseTool``, which can be passed directly into ``Agent(tools=[...])``
    """
    from langchain_core.tools import StructuredTool

    ex = executor or DifySandboxExecutor()
    desc = description or _DEFAULT_DESCRIPTION

    async def _arun(code: str) -> str:
        """Execute Python code, returning stdout (async path)."""
        success, output, metadata = await ex.execute(code)
        return _format_result(success, output, metadata)

    def _run(code: str) -> str:
        """Execute Python code, returning stdout (sync path, internally drives the async executor)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop → run asyncio.run directly
            return asyncio.run(_arun(code))
        # Already inside an event loop (rare: a sync tool called in an async context) → run in a separate thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_arun(code))).result()

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=name,
        description=desc,
    )
