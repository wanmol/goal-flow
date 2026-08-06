"""``agent_kit.middleware``：8 个 LangChain ``AgentMiddleware`` 的统一公开入口。

设计意图：让业务一个 import 就能拿到全套中间件，不需要分别知道老 ``harness.middleware``
与新顶层 ``middleware`` 的内部分布。

8 个中间件分两类：

**约束类（控制 agent loop 走向）**

- ``EntryGuardMiddleware``：入口短路（替老 ``before_call``）
- ``ModelSkipMiddleware``：跳过 LLM 调用（替老 ``should_run_agent``）
- ``ModelFailoverMiddleware``：主备模型切换（主模型不可用时切到备选）
- ``FallbackReplyMiddleware``：异常兜底（替老 ``on_failure``）
- ``SensitiveCheckMiddleware``：敏感词校验

**增强类（修改/扩展 model 调用）**

- ``ConversationHistoryMiddleware``：注入对话历史
- ``SkillAugmentationMiddleware``：拼 skill 详情进 prompt
- ``MetricsMiddleware``：自动埋点 model 调用延迟/失败
- ``StreamingBridgeMiddleware``：把 model 输出推到 stream callback
- ``LangfuseTracingMiddleware``：包围 agent 生命周期开/关 Langfuse span

以及一个工厂函数：

- ``make_dynamic_prompt_middleware``：从指定 source 构造动态 prompt 中间件
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
    # 约束类
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
    # 增强类
    "ConversationHistoryMiddleware",
    "merge_context_messages",
    "SkillAugmentationMiddleware",
    "MetricsMiddleware",
    "StreamingBridgeMiddleware",
    "LangfuseTracingMiddleware",
    # 工厂
    "make_dynamic_prompt_middleware",
    "DEFAULT_FALLBACK_PROMPT",
    "PromptSource",
]
