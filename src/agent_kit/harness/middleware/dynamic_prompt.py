"""DynamicPromptMiddleware: dynamic system prompt middleware.

Extracts the ``_dynamic_system_prompt_middleware`` from
``aira-agent-kit/agent_kit/runtimes/base.py:530-541`` into an independently importable factory
function, so business code can reuse it inside ``middleware_extra()`` without inheriting ``AgentRuntime``.

Design intent:
- ``AgentRuntime._dynamic_system_prompt_middleware()`` is a Runtime internal method;
  it can't be imported independently, let alone reused within middleware chains like ``ContextMiddleware``
- This module abstracts the "take the prompt from ``runtime.context.system_prompt`` (fall back if empty)"
  pattern into a top-level function, and allows business code to inject a custom ``prompt_source``
  (e.g. calling ``HARNESS_PROMPTS.render(...)`` or reading state)

Reuses LangChain's ``@dynamic_prompt`` decorator rather than reinventing it.
"""
from __future__ import annotations

from typing import Callable, Optional

from langchain.agents.middleware.types import ModelRequest, dynamic_prompt

DEFAULT_FALLBACK_PROMPT = "你是一个智能助手。"

PromptSource = Callable[[ModelRequest], Optional[str]]


def _read_system_prompt_from_context(request: ModelRequest) -> Optional[str]:
    """Default prompt_source: take from ``request.runtime.context.system_prompt``.

    Replicates the behavior of ``aira-agent-kit/agent_kit/runtimes/base.py:530-541``,
    for ``AgentRuntime`` subclasses to keep relying on.
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
    """Factory: return a LangChain ``@dynamic_prompt``-decorated middleware instance.

    Args:
        prompt_source: ``Callable[[ModelRequest], str | None]``; a non-empty string return value
            is used as the system prompt, while ``None``/empty string falls back to ``fallback``.
            Defaults to reading from ``request.runtime.context.system_prompt`` (compatible with the
            existing ``AgentRuntime`` subclasses' context_schema injection approach).
        fallback: the fallback prompt used when ``prompt_source`` yields no value.

    Usage::

        # Default: take from runtime.context.system_prompt
        md = make_dynamic_prompt_middleware()

        # Custom: pull from HARNESS_PROMPTS
        md = make_dynamic_prompt_middleware(
            lambda req: HARNESS_PROMPTS.render("my_agent.system", **req.state),
            fallback="You are an intelligent assistant.",
        )

        # Return it inside middleware_extra
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
