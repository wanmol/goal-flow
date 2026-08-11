"""Agent LangChain middleware (context, sensitive-word checks, entry short-circuit, model skip, error fallback, dynamic prompt, etc.)."""
from agent_kit.harness.middleware.agent_state import ContextAgentState
from agent_kit.harness.middleware.context_manager import (
    CallableContextManager,
    ContextAssembleFn,
    ContextManager,
    ConversationHistoryContextManager,
    DEFAULT_HISTORY_WINDOW_SIZE,
    default_context_manager,
    extract_turn_answer,
    extract_turn_query,
    history_dicts_to_messages,
    resolve_context_manager,
    should_save_turn,
)
from agent_kit.harness.middleware.context_middleware import (
    ContextMiddleware,
    merge_context_messages,
)
from agent_kit.harness.middleware.dynamic_prompt import (
    DEFAULT_FALLBACK_PROMPT,
    PromptSource,
    make_dynamic_prompt_middleware,
)
from agent_kit.harness.middleware.entry_guard import (
    EntryGuardMiddleware,
    GuardPredicate,
    GuardResult,
)
from agent_kit.harness.middleware.fallback_reply import (
    FallbackReplyMiddleware,
    OnErrorFn,
)
from agent_kit.harness.middleware.model_failover import (
    FailoverPredicate,
    ModelFailoverMiddleware,
    default_should_failover,
)
from agent_kit.harness.middleware.model_skip import (
    ModelSkipMiddleware,
    SkipPredicate,
    SkipResult,
)
from agent_kit.harness.middleware.sensitive_check_middleware import (
    SensitiveCheckMiddleware,
)

__all__ = [
    "ContextAgentState",
    "ContextManager",
    "ContextAssembleFn",
    "CallableContextManager",
    "ConversationHistoryContextManager",
    "DEFAULT_HISTORY_WINDOW_SIZE",
    "default_context_manager",
    "extract_turn_query",
    "extract_turn_answer",
    "history_dicts_to_messages",
    "resolve_context_manager",
    "should_save_turn",
    "ContextMiddleware",
    "merge_context_messages",
    "SensitiveCheckMiddleware",
    # P1: hooks pushed down into middleware
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
    "make_dynamic_prompt_middleware",
    "DEFAULT_FALLBACK_PROMPT",
    "PromptSource",
]
