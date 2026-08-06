"""
PromptRegistry：三层 prompt 加载（Langfuse → 本地文件 → 内置 fallback）。

设计要点：
- **三层 fallback**：依次尝试 Langfuse Prompt Management、本地模板文件、注册时给的 Python callable
- **任一层失败不影响下一层**：网络抖动 / Langfuse 配置错误 / 模板文件缺失，统统不会让业务挂掉
- **缓存**：成功命中后按 (name, source) 缓存；强制刷新用 ``invalidate(name)``
- **变量替换**：Jinja2 引擎；语法兼容 Langfuse Prompt Management 默认的 ``{{ var }}``
- **fallback_callable**：注册时可以传一个纯 Python 函数（签名 ``(**vars) -> str``），
  作为最低层兜底 —— 业务可以把原来的 ``_build_system_prompt`` 函数直接挂上来，
  做到"零行为差异迁移"
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
    """单个 prompt 的三层注册信息。"""

    name: str
    langfuse_name: Optional[str] = None
    local_template_path: Optional[str] = None
    fallback_callable: Optional[Callable[..., str]] = None
    _cached_template: dict = field(default_factory=dict)


class PromptRegistry:
    """三层 prompt 加载器。

    全局单例（``HARNESS_PROMPTS``）；业务在启动时 register，运行时 render。
    """

    def __init__(self) -> None:
        self._specs: dict[str, PromptSpec] = {}
        self._lock = threading.RLock()
        self._metric_emitter: Optional[Callable[..., None]] = None

    def set_metric_emitter(self, emitter: Callable[..., None]) -> None:
        """注入 metric 函数，签名 ``emitter(metric_name, **labels)``。"""
        self._metric_emitter = emitter

    def register(
        self,
        name: str,
        *,
        fallback_callable: Optional[Callable[..., str]] = None,
        local_template_path: Optional[str] = None,
        langfuse_name: Optional[str] = None,
    ) -> None:
        """注册一个 prompt 的三层来源。"""
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
        """三层加载并渲染。返回最终 prompt 字符串。

        第一个参数 ``prompt_name`` 是注册名；``**template_vars`` 传给各层模板变量
        （可与变量名 ``name`` 等任意关键字共存，不与本参数冲突）。
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
        """清空缓存。不传 name 清全部。"""
        with self._lock:
            if name is None:
                for s in self._specs.values():
                    s._cached_template.clear()
            elif name in self._specs:
                self._specs[name]._cached_template.clear()

    def reset(self) -> None:
        """清空全部 register 状态。单测/调试使用。"""
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
        """从 Langfuse Prompt Management 拉模板并渲染。None 表示该层未命中。"""
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
        """从本地 j2 文件加载模板并渲染。"""
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
