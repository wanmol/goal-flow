"""code_interpreter skill 的 in_process entry point。

``InProcessAdapter`` 期望 ``target`` 指向一个普通可调用对象（它用 LangChain ``@tool``
包装）。这里复用 ``DifySandboxExecutor`` 做实际执行，保持与
``agent_kit.tools.sandbox.make_sandbox_tool`` 同一套行为。
"""
from __future__ import annotations

import asyncio

from agent_kit.tools.sandbox.executor import DifySandboxExecutor
from agent_kit.tools.sandbox.tool import _format_result

# 模块级单例执行器：skill 无状态，复用同一个 executor 即可
_EXECUTOR = DifySandboxExecutor()


def run_python_code(code: str) -> str:
    """在隔离沙盒中执行 Python 代码并返回 stdout。

    适用于数据分析（pandas/numpy）、数值计算、格式转换、图表数据生成等需要真正
    运行代码才能得出结果的任务。必须用 print() 输出结果；禁止绘图库。

    :param code: 要执行的 Python 代码
    :returns: stdout 内容；失败时返回带 exit_code 的错误说明
    """
    success, output, metadata = asyncio.run(_EXECUTOR.execute(code))
    return _format_result(success, output, metadata)
