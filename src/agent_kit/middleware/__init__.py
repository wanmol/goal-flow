"""``agent_kit.middleware``: the unified public entry point for 8 LangChain ``AgentMiddleware``.

Design intent: let the business get the full set of middleware with a single import, without needing to
separately know the internal distribution between the old ``harness.middleware`` and the new top-level ``middleware``.

The 8 middleware fall into two categories:

**Constraint category (control the direction of the agent loop)**

- ``EntryGuardMiddleware``: entry short-circuit (replaces the old ``before_call``)
- ``ModelSkipMiddleware``: skip the LLM call (replaces the old ``should_run_agent``)
- ``ModelFailoverMiddleware``: primary/backup model switching (switch to the backup when the primary is unavailable)
- ``FallbackReplyMiddleware``: exception fallback (replaces the old ``on_failure``)
- ``SensitiveCheckMiddleware``: sensitive-word validation

**Enhancement category (modify/extend the model call)**

- ``ConversationHistoryMiddleware``: inject conversation history
- ``SkillAugmentationMiddleware``: splice skill details into the prompt
- ``MetricsMiddleware``: automatically instrument model call latency/failure
- ``StreamingBridgeMiddleware``: push model output to the stream callback
- ``LangfuseTracingMiddleware``: wrap the agent lifecycle to open/close a Langfuse span

Plus one factory function:

- ``make_dynamic_prompt_middleware``: build a dynamic prompt middleware from a given source
"""
from agent_kit.middleware.conversation_history import (
    ConversationHistoryMiddleware,
    merge_context_messages,
)
from agent_kit.middleware.dynamic_prompt import (
    DEFAULT_FALLBACK_PROMPT,
    PromptSource,
    make_dynamic_prompt_middleware,
)
from agent_kit.middleware.entry_guard import (
    EntryGuardMiddleware,
    GuardPredicate,
    GuardResult,
)
from agent_kit.middleware.fallback_reply import (
    FallbackReplyMiddleware,
    OnErrorFn,
)
from agent_kit.middleware.langfuse_tracing import LangfuseTracingMiddleware
from agent_kit.middleware.metrics import MetricsMiddleware
from agent_kit.middleware.model_failover import (
    FailoverPredicate,
    ModelFailoverMiddleware,
    default_should_failover,
)
from agent_kit.middleware.model_skip import (
    ModelSkipMiddleware,
    SkipPredicate,
    SkipResult,
)
from agent_kit.middleware.sensitive_check import SensitiveCheckMiddleware
from agent_kit.middleware.skill_augmentation import SkillAugmentationMiddleware
from agent_kit.middleware.streaming_bridge import StreamingBridgeMiddleware

__all__ = [
    # Constraint category
    "EntryGuardMiddleware",
    "GuardPredicate",
    "GuardResult",
    "ModelSkipMiddleware",
    "SkipPredicate",
    "SkipResult",
    "ModelFailoverMiddleware",
    "FailoverPredicate",
    "default_should_failover",
    "FallbackReplyMiddleware",
    "OnErrorFn",
    "SensitiveCheckMiddleware",
    # Enhancement category
    "ConversationHistoryMiddleware",
    "merge_context_messages",
    "SkillAugmentationMiddleware",
    "MetricsMiddleware",
    "StreamingBridgeMiddleware",
    "LangfuseTracingMiddleware",
    # Factory
    "make_dynamic_prompt_middleware",
    "DEFAULT_FALLBACK_PROMPT",
    "PromptSource",
]
