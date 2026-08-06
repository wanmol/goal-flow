"""
Model Router：task_type → LLM 实例的统一入口。

设计要点：
- agent_kit 不直接绑定任何具体 LLM 工厂（不依赖宿主仓库的 llm.LLM.create）
- 调用方在启动时通过 ``register_llm_factory(callable)`` 注入工厂函数
- Router 负责：task_type 路由 / fallback / 重试策略 / 缓存

工厂函数签名约定：
    factory(provider: str, model: str, temperature: float, max_tokens: int,
            **extra_kwargs) -> BaseChatModel
其中 extra_kwargs 会接到 timeout / max_retries 等可选项；
工厂函数可以选择性消费这些 kwargs（不支持的直接忽略）。

业务在自己的 task_type 上注册自定义配置：
    HARNESS_ROUTER.configure(
        "negotiation",
        provider="qwen", model="qwen-max", temperature=0.7,
    )

Runtime 拿 LLM：
    llm = HARNESS_ROUTER.get("negotiation")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from agent_kit.harness.settings import HARNESS_SETTINGS

logger = logging.getLogger(__name__)

LLMFactory = Callable[..., Any]


@dataclass
class TaskLLMConfig:
    """单个 task_type 的 LLM 配置。

    None 字段表示"用 HARNESS_SETTINGS.llm 的默认值"。
    业务可以只覆盖关心的字段（如只改 temperature），其它走 Harness 默认。
    """

    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None
    max_retries: Optional[int] = None
    extra: dict = field(default_factory=dict)

    def resolve(self) -> dict:
        """合并 HARNESS_SETTINGS.llm 默认值，返回完整 kwargs。"""
        d = HARNESS_SETTINGS.llm
        return {
            "provider": self.provider or d.provider,
            "model": self.model or d.default_model,
            "temperature": self.temperature if self.temperature is not None else d.default_temperature,
            "max_tokens": self.max_tokens or d.default_max_tokens,
            "timeout": self.timeout or d.request_timeout_seconds,
            "max_retries": self.max_retries if self.max_retries is not None else d.max_retries,
            **self.extra,
        }


class ModelRouter:
    """task_type → LLM 路由器。"""

    def __init__(self) -> None:
        self._factory: Optional[LLMFactory] = None
        self._configs: dict[str, TaskLLMConfig] = {}
        self._cache: dict[str, Any] = {}
        self._fallback_factory: Optional[LLMFactory] = None

    def register_llm_factory(self, factory: LLMFactory) -> None:
        """注入 LLM 工厂函数。Day4 默认调用方：``LLM.create``。"""
        self._factory = factory
        self._cache.clear()
        logger.info(f"ModelRouter: llm_factory registered ({factory!r})")

    def register_fallback_factory(self, factory: LLMFactory) -> None:
        """主工厂报错时的兜底工厂（如换提供方）。可选。"""
        self._fallback_factory = factory

    def configure(
        self,
        task_type: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        **extra,
    ) -> None:
        """为某个 task_type 注册/更新配置。"""
        if task_type in self._configs:
            old = self._configs[task_type]
            self._configs[task_type] = replace(
                old,
                provider=provider if provider is not None else old.provider,
                model=model if model is not None else old.model,
                temperature=temperature if temperature is not None else old.temperature,
                max_tokens=max_tokens if max_tokens is not None else old.max_tokens,
                timeout=timeout if timeout is not None else old.timeout,
                max_retries=max_retries if max_retries is not None else old.max_retries,
                extra={**old.extra, **extra},
            )
        else:
            self._configs[task_type] = TaskLLMConfig(
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                max_retries=max_retries,
                extra=extra,
            )
        self._cache.pop(task_type, None)
        logger.info(f"ModelRouter: configured task_type={task_type!r}")

    def get(self, task_type: str = "default") -> Any:
        """拿到 task_type 对应的 LLM 实例。"""
        if task_type in self._cache:
            return self._cache[task_type]

        if self._factory is None:
            raise RuntimeError(
                "ModelRouter: llm_factory not registered. "
                "Call HARNESS_ROUTER.register_llm_factory(...) at app startup."
            )

        cfg = self._configs.get(task_type) or TaskLLMConfig()
        kwargs = cfg.resolve()
        kwargs = self._sanitize_for_factory(kwargs)

        try:
            llm = self._factory(**kwargs)
        except Exception as e:
            # 兼容底层工厂不支持 timeout 等参数
            if "timeout" in str(e) or "max_retries" in str(e) or isinstance(e, TypeError):
                logger.warning(
                    f"ModelRouter: factory rejected kwargs ({e!r}); "
                    f"retrying without timeout/max_retries"
                )
                stripped = {k: v for k, v in kwargs.items() if k not in ("timeout", "max_retries")}
                try:
                    llm = self._factory(**stripped)
                except Exception as inner_e:
                    if self._fallback_factory is None:
                        raise inner_e
                    logger.warning(
                        f"ModelRouter: primary factory failed ({inner_e!r}); using fallback"
                    )
                    llm = self._fallback_factory(**kwargs)
            else:
                if self._fallback_factory is None:
                    raise
                logger.warning(
                    f"ModelRouter: primary factory failed ({e!r}); using fallback"
                )
                llm = self._fallback_factory(**kwargs)

        self._cache[task_type] = llm
        logger.info(
            f"ModelRouter: created LLM for task_type={task_type!r} "
            f"(model={kwargs.get('model')}, temperature={kwargs.get('temperature')})"
        )
        return llm

    def _sanitize_for_factory(self, kwargs: dict) -> dict:
        """业务工厂可能不认 None；把 None 字段去掉以便用工厂自己的默认。"""
        return {k: v for k, v in kwargs.items() if v is not None}

    def reset(self) -> None:
        """清空缓存（工厂/配置保留）。单测/调试用。"""
        self._cache.clear()

    def reset_all(self) -> None:
        """清空缓存 + 配置 + 工厂。仅单测使用。"""
        self._cache.clear()
        self._configs.clear()
        self._factory = None
        self._fallback_factory = None


HARNESS_ROUTER = ModelRouter()
