"""in_process entry point for the code_interpreter skill.

``InProcessAdapter`` expects ``target`` to point to a plain callable (which it wraps with LangChain ``@tool``).
Here we reuse ``DifySandboxExecutor`` for the actual execution, keeping the same behavior as
``agent_kit.tools.sandbox.make_sandbox_tool``.
"""
from __future__ import annotations

import asyncio

from agent_kit.tools.sandbox.executor import DifySandboxExecutor
from agent_kit.tools.sandbox.tool import _format_result

# Module-level singleton executor: the skill is stateless, so reusing one executor is fine
_EXECUTOR = DifySandboxExecutor()


def run_python_code(code: str) -> str:
    """Execute Python code in an isolated sandbox and return stdout.

    Suitable for tasks that require actually running code to get a result, such as data analysis
    (pandas/numpy), numerical computation, format conversion, and chart data generation. Must use
    print() to output the result; plotting libraries are prohibited.

    :param code: the Python code to execute
    :returns: stdout content; on failure returns an error description with exit_code
    """
    success, output, metadata = asyncio.run(_EXECUTOR.execute(code))
    return _format_result(success, output, metadata)
