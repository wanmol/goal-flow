"""HarnessSettings: cross-business common Agent governance configuration.

Design principles:
- Only hold "cross-business common" config (LLM defaults, metric naming, log level, fallback policy)
- Business-specific config (such as requirement_collection's max_turns / score_threshold)
  stays in the business module's own settings.py, **not lifted up into the Harness** -- to avoid becoming a catch-all
- Business settings can derive default values from HARNESS_SETTINGS (after Day4)

Relationship to the host repo's existing ``node/employer/requirement_collection/settings.py``:
- The latter continues to exist as the business-specific tuning center
- The latter's ``LLMSettings`` section can optionally reference the defaults of ``HARNESS_SETTINGS.llm``
  (adjusted uniformly when the Model Router is implemented on Day4)

Environment variable override: deliberately not done at the Harness layer. If the business needs env injection,
just inject a custom ``HarnessSettings(...)`` instance at the call site.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMDefaults(BaseModel):
    """Cross-business common LLM default values.

    The business can override:
    - The bargaining node needs 32k context -> change default_max_tokens in the business Settings
    - The review node needs a colder temperature -> change default_temperature in the business Settings

    What's placed here are "reasonable defaults when there are no special business needs".
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
    """metric / log / trace related. Used by the Day7 Observability abstraction."""

    langfuse_enabled: bool = Field(
        default=True,
        description="是否启用 Langfuse trace；False 时 Runtime 自动降级为 noop",
    )


class FallbackPolicy(BaseModel):
    """The global fallback policy when the Agent fails. Readable by Runtime.on_failure()."""

    reply: str = Field(
        default="请继续提供您的需求信息，我们将为您精准匹配。",
        description="Agent 异常时统一兜底话术；Runtime.fallback_reply 优先级更高",
    )


class HarnessSettings(BaseModel):
    """The unified configuration entry point for the Harness governance base.

    For unit tests / debugging you can construct a custom instance to override the global singleton:

        custom = HarnessSettings(llm=LLMDefaults(default_model="qwen-max"))
        HARNESS_SETTINGS = custom   # not recommended to do this in production code
    """

    llm: LLMDefaults = Field(default_factory=LLMDefaults)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    fallback: FallbackPolicy = Field(default_factory=FallbackPolicy)


HARNESS_SETTINGS = HarnessSettings()
