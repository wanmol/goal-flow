"""SkillMatcher：基于 LLM 的 skill 匹配器。

设计：
- LLM 通过 ``HARNESS_ROUTER.get(task_type)`` 拿，业务零硬依赖
- prompt 通过 ``HARNESS_PROMPTS.render(prompt_name, query=..., skills_json=...)`` 渲染
- 内置 fallback prompt 已经在 ``ensure_default_prompt_registered()`` 里注册到 HARNESS_PROMPTS，
  业务什么都不配也能跑（用 LLM 默认 + fallback prompt）
- 失败容忍：LLM 异常 / JSON 解析失败 → 返回空列表，**绝不让 skill 匹配拖垮主 Agent**

业务可注入自定义 matcher：实现 ``Matcher`` 协议（``match(query, manifests, top_k, threshold) -> list[MatchResult]``）
即可，例如 embedding-based、规则-based。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from agent_kit.skills.models import MatchResult, SkillManifest

logger = logging.getLogger(__name__)


DEFAULT_TASK_TYPE = "agent_kit.skill_match"
DEFAULT_PROMPT_NAME = "agent_kit.skill_match"


# ───────────────────── Matcher 协议 ─────────────────────

@runtime_checkable
class Matcher(Protocol):
    """业务可注入的 matcher 协议。"""

    def match(
        self,
        query: str,
        manifests: list[SkillManifest],
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[MatchResult]: ...


# ───────────────────── 默认 LLM Matcher ─────────────────────

class SkillMatcher:
    """默认 LLM-based matcher。"""

    def __init__(
        self,
        *,
        task_type: str = DEFAULT_TASK_TYPE,
        prompt_name: str = DEFAULT_PROMPT_NAME,
        llm_factory: Optional[Callable[[], Any]] = None,
    ):
        """
        Args:
            task_type: HARNESS_ROUTER 路由 key；业务可在启动时
                ``HARNESS_ROUTER.configure("agent_kit.skill_match", ...)`` 自定义模型
            prompt_name: HARNESS_PROMPTS 注册的 prompt 名；业务可注册同名 prompt 覆盖
            llm_factory: 单测专用注入；不为 None 时跳过 HARNESS_ROUTER
        """
        self._task_type = task_type
        self._prompt_name = prompt_name
        self._llm_factory = llm_factory

    def match(
        self,
        query: str,
        manifests: list[SkillManifest],
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[MatchResult]:
        if not manifests:
            return []

        # 渲染 prompt
        try:
            prompt_text = self._render_prompt(query, manifests)
        except Exception as e:
            logger.warning("SkillMatcher: prompt render failed: %s", e)
            return []

        # 拿 LLM
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("SkillMatcher: get LLM failed: %s", e)
            return []

        # 调用 LLM
        try:
            from langchain_core.messages import HumanMessage

            response = llm.invoke([HumanMessage(content=prompt_text)])
            content = getattr(response, "content", "") or ""
        except Exception as e:
            logger.warning("SkillMatcher: LLM invoke failed: %s", e)
            return []

        # 解析 JSON
        results = _parse_response(content)
        results = [r for r in results if r.confidence >= threshold]
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    # ────────── internals ──────────

    def _get_llm(self):
        if self._llm_factory is not None:
            return self._llm_factory()
        from agent_kit.harness.model_router import HARNESS_ROUTER

        return HARNESS_ROUTER.get(self._task_type)

    def _render_prompt(self, query: str, manifests: list[SkillManifest]) -> str:
        from agent_kit.harness.prompt_registry import HARNESS_PROMPTS

        skills_json = json.dumps(
            [
                {"skill_id": m.skill_id, "name": m.name, "description": m.description}
                for m in manifests
            ],
            ensure_ascii=False,
        )
        return HARNESS_PROMPTS.render(
            self._prompt_name, query=query, skills_json=skills_json
        )


# ───────────────────── 默认 fallback prompt ─────────────────────

DEFAULT_PROMPT_TEMPLATE = """\
你是一个技能匹配器。给定用户的 query 和可用技能列表，选出与 query 最相关的技能。

## 用户 query
{query}

## 可用技能（JSON 数组）
{skills_json}

## 输出要求
返回一个 JSON 数组，每个元素是一个对象，包含字段：
- skill_id（与输入一致）
- skill_name（与输入一致）
- confidence（0.0 到 1.0 的浮点数，0.0=无关，1.0=完全匹配）
- reason（一句话说明为什么匹配，可选）

只返回 JSON，不要任何额外文字、不要 markdown 代码块。如果没有任何技能匹配，返回 []。
"""


def _default_prompt_fallback(*, query: str = "", skills_json: str = "", **_) -> str:
    """HARNESS_PROMPTS fallback callable。业务可通过注册同名 prompt 覆盖。"""
    return DEFAULT_PROMPT_TEMPLATE.format(query=query, skills_json=skills_json)


def ensure_default_prompt_registered(prompt_name: str = DEFAULT_PROMPT_NAME) -> None:
    """把默认 skill match prompt 注册到 HARNESS_PROMPTS（幂等）。

    SkillOrchestrator.match_and_augment() 会自动调用这个；业务也可以手动调一次后
    通过 ``HARNESS_PROMPTS.register()`` 用自己的版本覆盖。
    """
    from agent_kit.harness.prompt_registry import HARNESS_PROMPTS

    # 已注册同名的就别覆盖（业务可能已经注册了 Langfuse 版本）
    if prompt_name in HARNESS_PROMPTS._specs:  # type: ignore[attr-defined]
        return
    HARNESS_PROMPTS.register(prompt_name, fallback_callable=_default_prompt_fallback)


# ───────────────────── JSON 解析 ─────────────────────

def _parse_response(content: str) -> list[MatchResult]:
    """LLM 输出 → MatchResult 列表。容忍 markdown 代码块、单对象、非法项。"""
    if not content:
        return []
    cleaned = content.strip()
    # 去掉 markdown 代码块包裹
    if cleaned.startswith("```"):
        # 去第一行 ``` 或 ```json
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("SkillMatcher: JSON decode failed: %s; raw=%r", e, content[:200])
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    out: list[MatchResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            out.append(MatchResult(**item))
        except Exception as e:
            logger.warning("SkillMatcher: invalid match item %r: %s", item, e)
    return out
