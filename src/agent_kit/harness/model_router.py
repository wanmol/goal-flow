"""
Model Router: a unified entry point for task_type → LLM instance.

Design points:
- agent_kit does not directly bind any concrete LLM factory (no dependency on the host repo's llm.LLM.create)
- The caller injects a factory function at startup via ``register_llm_factory(callable)``
- The Router is responsible for: task_type routing / fallback / retry strategy / caching

Factory function signature convention:
    factory(provider: str, model: str, temperature: float, max_tokens: int,
            **extra_kwargs) -> BaseChatModel
where extra_kwargs receives optional items like timeout / max_retries;
the factory may consume these kwargs selectively (ignoring unsupported ones outright).

Business code registers custom config on its own task_type:
    HARNESS_ROUTER.configure(
        "negotiation",
        provider="qwen", model="qwen-max", temperature=0.7,
    )

Runtime fetches an LLM:
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
    """LLM config for a single task_type.

    A None field means "use the default value from HARNESS_SETTINGS.llm".
    Business code can override only the fields it cares about (e.g. only temperature), leaving the rest to Harness defaults.
    """

    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None
    max_retries: Optional[int] = None
    extra: dict = field(default_factory=dict)

    def resolve(self) -> dict:
        """Merge in the HARNESS_SETTINGS.llm defaults and return the complete kwargs."""
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
    """task_type → LLM router."""

    def __init__(self) -> None:
        self._factory: Optional[LLMFactory] = None
        self._configs: dict[str, TaskLLMConfig] = {}
        self._cache: dict[str, Any] = {}
        self._fallback_factory: Optional[LLMFactory] = None

    def register_llm_factory(self, factory: LLMFactory) -> None:
        """Inject the LLM factory function. Day4 default caller: ``LLM.create``."""
        self._factory = factory
        self._cache.clear()
        logger.info(f"ModelRouter: llm_factory registered ({factory!r})")

    def register_fallback_factory(self, factory: LLMFactory) -> None:
        """Fallback factory used when the primary factory errors (e.g. switching providers). Optional."""
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
        """Register/update config for a given task_type."""
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
        """Get the LLM instance corresponding to task_type."""
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
            # Compatible with underlying factories that don't support params like timeout
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
        """Business factories may not accept None; drop None fields so the factory's own defaults apply."""
        return {k: v for k, v in kwargs.items() if v is not None}

    def reset(self) -> None:
        """Clear the cache (factory/config retained). For unit tests/debugging."""
        self._cache.clear()

    def reset_all(self) -> None:
        """Clear cache + config + factory. Unit-test use only."""
        self._cache.clear()
        self._configs.clear()
        self._factory = None
        self._fallback_factory = None


HARNESS_ROUTER = ModelRouter()
