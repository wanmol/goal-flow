"""
PromptRegistry: three-layer prompt loading (Langfuse -> local file -> built-in fallback).

Design points:
- **Three-layer fallback**: tries Langfuse Prompt Management, the local template file, and the Python callable given at registration, in order
- **A failure in any layer does not affect the next**: network jitter / Langfuse misconfiguration / missing template file will never take down the business
- **Cache**: after a successful hit, cached by (name, source); force a refresh with ``invalidate(name)``
- **Variable substitution**: Jinja2 engine; syntax compatible with Langfuse Prompt Management's default ``{{ var }}``
- **fallback_callable**: at registration you can pass a pure Python function (signature ``(**vars) -> str``)
  as the lowest-layer safety net -- the business can hang its original ``_build_system_prompt`` function
  directly onto it, achieving a "zero-behavior-difference migration"
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from agent_kit.harness.settings import HARNESS_SETTINGS

logger = logging.getLogger(__name__)

SOURCE_LANGFUSE = "langfuse"
SOURCE_LOCAL = "local"
SOURCE_FALLBACK = "fallback"


@dataclass
class PromptSpec:
    """Three-layer registration info for a single prompt."""

    name: str
    langfuse_name: Optional[str] = None
    local_template_path: Optional[str] = None
    fallback_callable: Optional[Callable[..., str]] = None
    _cached_template: dict = field(default_factory=dict)


class PromptRegistry:
    """Three-layer prompt loader.

    Global singleton (``HARNESS_PROMPTS``); the business registers at startup and renders at runtime.
    """

    def __init__(self) -> None:
        self._specs: dict[str, PromptSpec] = {}
        self._lock = threading.RLock()
        self._metric_emitter: Optional[Callable[..., None]] = None

    def set_metric_emitter(self, emitter: Callable[..., None]) -> None:
        """Inject the metric function, signature ``emitter(metric_name, **labels)``."""
        self._metric_emitter = emitter

    def register(
        self,
        name: str,
        *,
        fallback_callable: Optional[Callable[..., str]] = None,
        local_template_path: Optional[str] = None,
        langfuse_name: Optional[str] = None,
    ) -> None:
        """Register the three-layer sources for a prompt."""
        with self._lock:
            spec = PromptSpec(
                name=name,
                langfuse_name=langfuse_name or name,
                local_template_path=local_template_path,
                fallback_callable=fallback_callable,
            )
            self._specs[name] = spec
        logger.info(
            f"PromptRegistry: registered {name!r} "
            f"(langfuse={spec.langfuse_name}, local={spec.local_template_path}, "
            f"fallback={'yes' if fallback_callable else 'no'})"
        )

    def render(self, prompt_name: str, **template_vars) -> str:
        """Load and render across the three layers. Returns the final prompt string.

        The first argument ``prompt_name`` is the registration name; ``**template_vars`` are passed to each
        layer's template variables (can coexist with any keyword such as the variable name ``name``, without
        conflicting with this parameter).
        """
        spec = self._specs.get(prompt_name)
        if spec is None:
            raise KeyError(
                f"PromptRegistry: prompt {prompt_name!r} not registered; "
                "call HARNESS_PROMPTS.register(name=...) at startup."
            )

        if HARNESS_SETTINGS.observability.langfuse_enabled:
            try:
                text = self._render_langfuse(spec, template_vars)
                if text:
                    self._emit("prompt_render_hit", prompt=prompt_name, source=SOURCE_LANGFUSE)
                    return text
            except Exception as e:
                logger.warning(
                    f"PromptRegistry.render({prompt_name!r}): Langfuse layer failed: {e}"
                )

        if spec.local_template_path:
            try:
                text = self._render_local(spec, template_vars)
                if text:
                    self._emit("prompt_render_hit", prompt=prompt_name, source=SOURCE_LOCAL)
                    return text
            except Exception as e:
                logger.warning(
                    f"PromptRegistry.render({prompt_name!r}): local layer failed: {e}"
                )

        if spec.fallback_callable is not None:
            try:
                text = spec.fallback_callable(**template_vars)
                self._emit("prompt_render_hit", prompt=prompt_name, source=SOURCE_FALLBACK)
                return text
            except Exception as e:
                logger.error(
                    f"PromptRegistry.render({prompt_name!r}): fallback layer failed: {e}",
                    exc_info=True,
                )

        logger.error(f"PromptRegistry.render({prompt_name!r}): all 3 layers missed")
        self._emit("prompt_render_miss", prompt=prompt_name)
        return ""

    def invalidate(self, name: Optional[str] = None) -> None:
        """Clear the cache. Clears everything if no name is passed."""
        with self._lock:
            if name is None:
                for s in self._specs.values():
                    s._cached_template.clear()
            elif name in self._specs:
                self._specs[name]._cached_template.clear()

    def reset(self) -> None:
        """Clear all register state. For unit tests / debugging."""
        with self._lock:
            self._specs.clear()
        self._metric_emitter = None

    def _emit(self, metric: str, **labels) -> None:
        if self._metric_emitter is None:
            return
        try:
            self._metric_emitter(metric, **labels)
        except Exception as e:
            logger.warning(f"PromptRegistry._emit({metric!r}) failed: {e}")

    def _render_langfuse(self, spec: PromptSpec, vars: dict) -> Optional[str]:
        """Pull the template from Langfuse Prompt Management and render it. None means this layer missed."""
        try:
            from langfuse import get_client
        except ImportError:
            return None
        try:
            client = get_client()
            prompt = client.get_prompt(spec.langfuse_name)
        except Exception:
            return None
        if prompt is None:
            return None
        try:
            return prompt.compile(**vars)
        except Exception as e:
            logger.warning(
                f"PromptRegistry._render_langfuse({spec.name!r}): compile failed: {e}"
            )
            return None

    def _render_local(self, spec: PromptSpec, vars: dict) -> Optional[str]:
        """Load the template from a local j2 file and render it."""
        path = Path(spec.local_template_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None
        try:
            from jinja2 import Template
        except ImportError:
            logger.warning(
                f"PromptRegistry._render_local({spec.name!r}): jinja2 not installed; "
                "skipping local layer"
            )
            return None
        mtime = path.stat().st_mtime
        cache_key = ("local", mtime)
        if cache_key in spec._cached_template:
            tpl = spec._cached_template[cache_key]
        else:
            tpl = Template(path.read_text(encoding="utf-8"))
            spec._cached_template.clear()
            spec._cached_template[cache_key] = tpl
        return tpl.render(**vars)


HARNESS_PROMPTS = PromptRegistry()
