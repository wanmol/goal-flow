"""``make_dynamic_prompt_middleware`` top-level public entry point."""
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
