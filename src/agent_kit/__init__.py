"""agent_kit: cross-form Agent toolkit + Harness governance foundation."""
# ── Legacy API (still usable; P2 added a DeprecationWarning) ──────────────
from agent_kit.runtimes.base import AgentRuntime, AgentResult, classify_error
from agent_kit.runtimes.deep_agent import DeepAgentRuntime
from agent_kit.runtimes.create_agent import CreateAgentRuntime
from agent_kit.runtimes.state_graph import StateGraphRuntime
from agent_kit.harness import (
    HARNESS_SETTINGS,
    HarnessSettings,
    LLMDefaults,
    ObservabilitySettings,
    FallbackPolicy,
    HARNESS_ROUTER,
    ModelRouter,
    TaskLLMConfig,
    HARNESS_PROMPTS,
    PromptRegistry,
    PromptSpec,
    SOURCE_LANGFUSE,
    SOURCE_LOCAL,
    SOURCE_FALLBACK,
    HARNESS_OBS,
    Observability,
    SpanContext,
    HARNESS_PROFILES,
    HarnessProfile,
    ProfileRegistry,
)
from agent_kit.harness.middleware import (
    EntryGuardMiddleware,
    GuardPredicate,
    GuardResult,
    ModelSkipMiddleware,
    SkipPredicate,
    SkipResult,
    FallbackReplyMiddleware,
    OnErrorFn,
    make_dynamic_prompt_middleware,
    DEFAULT_FALLBACK_PROMPT,
    PromptSource,
)
from agent_kit.integrations import HarnessBacked

# ── New API (P3, ADR-003) ────────────────────────────────────────
from agent_kit.agent import Agent
from agent_kit.harness.harness import Harness, default_harness
from agent_kit.graphs import (
    GraphBuilder,
    ReactGraphBuilder,
    DeepGraphBuilder,
    CustomGraphBuilder,
)
from agent_kit.middleware import (
    ConversationHistoryMiddleware,
    SensitiveCheckMiddleware,
    SkillAugmentationMiddleware,
    MetricsMiddleware,
    StreamingBridgeMiddleware,
    LangfuseTracingMiddleware,
)
from agent_kit.stores import ConversationStore, MessageServiceStore
from agent_kit.tools import InjectedAgentOutput, InjectedState

__all__ = [
    # ── Legacy API ───────────────────────────────────────
    "AgentRuntime",
    "AgentResult",
    "classify_error",
    "DeepAgentRuntime",
    "CreateAgentRuntime",
    "StateGraphRuntime",
    "HARNESS_SETTINGS",
    "HarnessSettings",
    "LLMDefaults",
    "ObservabilitySettings",
    "FallbackPolicy",
    "HARNESS_ROUTER",
    "ModelRouter",
    "TaskLLMConfig",
    "HARNESS_PROMPTS",
    "PromptRegistry",
    "PromptSpec",
    "SOURCE_LANGFUSE",
    "SOURCE_LOCAL",
    "SOURCE_FALLBACK",
    "HARNESS_OBS",
    "Observability",
    "SpanContext",
    "HARNESS_PROFILES",
    "HarnessProfile",
    "ProfileRegistry",
    "HarnessBacked",
    "EntryGuardMiddleware",
    "GuardPredicate",
    "GuardResult",
    "ModelSkipMiddleware",
    "SkipPredicate",
    "SkipResult",
    "FallbackReplyMiddleware",
    "OnErrorFn",
    "make_dynamic_prompt_middleware",
    "DEFAULT_FALLBACK_PROMPT",
    "PromptSource",
    # ── New API (P3, ADR-003) ────────────────────────
    "Agent",
    "Harness",
    "default_harness",
    "GraphBuilder",
    "ReactGraphBuilder",
    "DeepGraphBuilder",
    "CustomGraphBuilder",
    "ConversationHistoryMiddleware",
    "SensitiveCheckMiddleware",
    "SkillAugmentationMiddleware",
    "MetricsMiddleware",
    "StreamingBridgeMiddleware",
    "LangfuseTracingMiddleware",
    "ConversationStore",
    "MessageServiceStore",
    "InjectedAgentOutput",
    "InjectedState",
]
__version__ = "2.0.0"
