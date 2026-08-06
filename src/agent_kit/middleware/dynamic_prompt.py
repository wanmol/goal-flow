"""``make_dynamic_prompt_middleware`` 顶层公开入口。"""
from agent_kit.harness.middleware.dynamic_prompt import (
    DEFAULT_FALLBACK_PROMPT,
    PromptSource,
    make_dynamic_prompt_middleware,
)

__all__ = [
    "make_dynamic_prompt_middleware",
    "DEFAULT_FALLBACK_PROMPT",
    "PromptSource",
]
