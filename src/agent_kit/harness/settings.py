"""HarnessSettings：跨业务通用的 Agent 治理配置。

设计原则：
- 只放"跨业务通用"的配置（LLM 默认、metric 命名、log level、fallback 策略）
- 业务专属配置（如 requirement_collection 的 max_turns / score_threshold）
  继续放在业务模块自己的 settings.py，**不上抽到 Harness**——避免成为大杂烩
- 业务 settings 可以从 HARNESS_SETTINGS 派生默认值（Day4 之后）

与宿主仓库现有 ``node/employer/requirement_collection/settings.py`` 的关系：
- 后者继续存在，作为业务专属调参中心
- 后者的 ``LLMSettings`` 节可以选择性地引用 ``HARNESS_SETTINGS.llm`` 的默认值
  （Day4 实施 Model Router 时统一调整）

环境变量覆盖：故意不在 Harness 层做。如果业务需要 env 注入，
在调用方注入 ``HarnessSettings(...)`` 自定义实例即可。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMDefaults(BaseModel):
    """跨业务通用的 LLM 默认值。

    业务可以重写：
    - 议价节点要 32k context → 在业务 Settings 里改 default_max_tokens
    - 复核节点要更冷温度 → 在业务 Settings 里改 default_temperature

    这里放的是"没有业务特殊需求时的合理默认"。
    """

    provider: str = Field(default="qwen", description="LangChain LLM 提供方标识")
    default_model: str = Field(default="qwen-plus", description="主模型名")
    default_temperature: float = Field(default=0.3, description="对话生成默认温度")
    default_max_tokens: int = Field(default=2000, description="生成默认 max_tokens")
    extract_temperature: float = Field(default=0.1, description="字段提取/分类温度（追求确定性）")
    request_timeout_seconds: float = Field(
        default=30.0, description="单次 LLM 调用超时（秒），Day4 Model Router 使用"
    )
    max_retries: int = Field(
        default=2, description="LLM 调用失败重试次数（不含首次），Day4 Model Router 使用"
    )


class ObservabilitySettings(BaseModel):
    """metric / log / trace 相关。Day7 Observability 抽象使用。"""

    langfuse_enabled: bool = Field(
        default=True,
        description="是否启用 Langfuse trace；False 时 Runtime 自动降级为 noop",
    )


class FallbackPolicy(BaseModel):
    """Agent 失败时的全局兜底策略。Runtime.on_failure() 可读取。"""

    reply: str = Field(
        default="请继续提供您的需求信息，我们将为您精准匹配。",
        description="Agent 异常时统一兜底话术；Runtime.fallback_reply 优先级更高",
    )


class HarnessSettings(BaseModel):
    """Harness 治理底座的统一配置入口。

    单测/调试时可以构造自定义实例覆盖全局单例：

        custom = HarnessSettings(llm=LLMDefaults(default_model="qwen-max"))
        HARNESS_SETTINGS = custom   # 不推荐在生产代码里这么做
    """

    llm: LLMDefaults = Field(default_factory=LLMDefaults)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    fallback: FallbackPolicy = Field(default_factory=FallbackPolicy)


HARNESS_SETTINGS = HarnessSettings()
