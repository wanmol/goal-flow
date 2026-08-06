"""把 ``BaseSandboxExecutor`` 封装为 LangChain ``BaseTool``。

设计意图：代码执行是模型自主调用的能力（function calling），不是切面，因此包装为
tool 而非 middleware。模型判断「需要执行代码才能得出结果」时才调用。

适用场景（写进 tool description 引导模型）：
- 数据分析与统计计算（pandas / numpy）
- 数值计算与复杂公式（循环 / 条件 / 多步骤）
- 格式转换（JSON 解析 / 数据整理）
- 图表数据生成（输出数据，不出图——沙盒禁止绘图库）
- 任何需要执行代码才能得出结果的任务

用法::

    from agent_kit.tools.sandbox import make_sandbox_tool

    agent = MyAgent(tools=[make_sandbox_tool()])              # 默认 Dify sandbox
    agent = MyAgent(tools=[make_sandbox_tool(MyExecutor())])  # 自定义执行器
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
    """把 ``(success, output, metadata)`` 渲染为给模型看的文本。

    成功直接返回 stdout；失败带上 exit_code 让模型能判断是「代码错」还是
    「服务不可用」并据此纠正。
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
    """构造一个执行 Python 代码的 LangChain ``BaseTool``。

    :param executor: ``BaseSandboxExecutor`` 实例；默认 ``DifySandboxExecutor()``
    :param name: tool 名（LangChain function-calling 暴露的名字），默认 ``run_python_code``
    :param description: 覆盖默认 description（默认已包含适用场景与约束说明）
    :returns: LangChain ``BaseTool``，可直接传入 ``Agent(tools=[...])``
    """
    from langchain_core.tools import StructuredTool

    ex = executor or DifySandboxExecutor()
    desc = description or _DEFAULT_DESCRIPTION

    async def _arun(code: str) -> str:
        """执行 Python 代码，返回 stdout（异步路径）。"""
        success, output, metadata = await ex.execute(code)
        return _format_result(success, output, metadata)

    def _run(code: str) -> str:
        """执行 Python 代码，返回 stdout（同步路径，内部驱动 async executor）。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无运行中的事件循环 → 直接 asyncio.run
            return asyncio.run(_arun(code))
        # 已在事件循环里（罕见：同步 tool 在 async 上下文被调）→ 独立线程跑
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_arun(code))).result()

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=name,
        description=desc,
    )
