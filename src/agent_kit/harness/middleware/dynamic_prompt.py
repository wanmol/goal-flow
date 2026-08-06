"""DynamicPromptMiddleware：动态 system prompt 中间件。

把 ``aira-agent-kit/agent_kit/runtimes/base.py:530-541`` 的
``_dynamic_system_prompt_middleware`` 提取为可独立 import 的工厂函数，
便于业务在 ``middleware_extra()`` 里复用而无需继承 ``AgentRuntime``。

设计意图：
- ``AgentRuntime._dynamic_system_prompt_middleware()`` 是 Runtime 内部方法，
  外部无法独立 import，更不能在 ``ContextMiddleware`` 等中间件链里复用
- 本模块把"从 ``runtime.context.system_prompt`` 取 prompt（空则回 fallback）"
  这个模式抽成顶层函数，并允许业务注入自定义 ``prompt_source``（如调
  ``HARNESS_PROMPTS.render(...)`` 或读 state）

复用 LangChain ``@dynamic_prompt`` 装饰器，不重新发明。
"""
from __future__ import annotations

from typing import Callable, Optional

from langchain.agents.middleware.types import ModelRequest, dynamic_prompt

DEFAULT_FALLBACK_PROMPT = "你是一个智能助手。"

PromptSource = Callable[[ModelRequest], Optional[str]]


def _read_system_prompt_from_context(request: ModelRequest) -> Optional[str]:
    """默认 prompt_source：从 ``request.runtime.context.system_prompt`` 取。

    复刻 ``aira-agent-kit/agent_kit/runtimes/base.py:530-541`` 的行为，
    供 ``AgentRuntime`` 子类继续依赖。
    """
    ctx = getattr(request.runtime, "context", None)
    if ctx is None:
        return None
    value = getattr(ctx, "system_prompt", None)
    if not value and hasattr(ctx, "get"):
        value = ctx.get("system_prompt")
    return str(value) if value else None


def make_dynamic_prompt_middleware(
    prompt_source: PromptSource = _read_system_prompt_from_context,
    *,
    fallback: str = DEFAULT_FALLBACK_PROMPT,
):
    """工厂：返回一个 LangChain ``@dynamic_prompt`` 装饰的中间件实例。

    Args:
        prompt_source: ``Callable[[ModelRequest], str | None]``；返回非空字符串
            则作为 system prompt 使用，返回 ``None``/空串则回退到 ``fallback``。
            默认从 ``request.runtime.context.system_prompt`` 读取（兼容现有
            ``AgentRuntime`` 子类的 context_schema 注入方式）。
        fallback: ``prompt_source`` 取不到值时使用的兜底 prompt。

    用法::

        # 默认：从 runtime.context.system_prompt 取
        md = make_dynamic_prompt_middleware()

        # 自定义：从 HARNESS_PROMPTS 拉
        md = make_dynamic_prompt_middleware(
            lambda req: HARNESS_PROMPTS.render("my_agent.system", **req.state),
            fallback="你是一个智能助手。",
        )

        # 在 middleware_extra 里返回
        class MyAgent(CreateAgentRuntime[MyResult]):
            def middleware_extra(self):
                return [make_dynamic_prompt_middleware()]
    """

    @dynamic_prompt
    def _md(request: ModelRequest) -> str:
        try:
            value = prompt_source(request)
        except Exception:
            value = None
        return value if value else fallback

    return _md
