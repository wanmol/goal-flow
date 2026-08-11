"""SkillMatcher: an LLM-based skill matcher.

Design:
- The LLM is obtained via ``HARNESS_ROUTER.get(task_type)``, zero hard dependency for business code
- The prompt is rendered via ``HARNESS_PROMPTS.render(prompt_name, query=..., skills_json=...)``
- The built-in fallback prompt is already registered to HARNESS_PROMPTS in ``ensure_default_prompt_registered()``,
  so it runs even with no business configuration (using the LLM default + fallback prompt)
- Failure tolerant: LLM exception / JSON parse failure → return an empty list, **never let skill matching drag down the main Agent**

Business can inject a custom matcher: just implement the ``Matcher`` protocol (``match(query, manifests, top_k, threshold) -> list[MatchResult]``),
e.g. embedding-based or rule-based.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from agent_kit.skills.models import MatchResult, SkillManifest

logger = logging.getLogger(__name__)


DEFAULT_TASK_TYPE = "agent_kit.skill_match"
DEFAULT_PROMPT_NAME = "agent_kit.skill_match"


# ───────────────────── Matcher protocol ─────────────────────

@runtime_checkable
class Matcher(Protocol):
    """The matcher protocol that business code can inject."""

    def match(
        self,
        query: str,
        manifests: list[SkillManifest],
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[MatchResult]: ...


# ───────────────────── Default LLM Matcher ─────────────────────

class SkillMatcher:
    """The default LLM-based matcher."""

    def __init__(
        self,
        *,
        task_type: str = DEFAULT_TASK_TYPE,
        prompt_name: str = DEFAULT_PROMPT_NAME,
        llm_factory: Optional[Callable[[], Any]] = None,
    ):
        """
        Args:
            task_type: the HARNESS_ROUTER routing key; business can customize the model at startup via
                ``HARNESS_ROUTER.configure("agent_kit.skill_match", ...)``
            prompt_name: the prompt name registered in HARNESS_PROMPTS; business can register a same-named prompt to override
            llm_factory: injection for unit tests only; when not None, skips HARNESS_ROUTER
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

        # Render prompt
        try:
            prompt_text = self._render_prompt(query, manifests)
        except Exception as e:
            logger.warning("SkillMatcher: prompt render failed: %s", e)
            return []

        # Get LLM
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("SkillMatcher: get LLM failed: %s", e)
            return []

        # Invoke LLM
        try:
            from langchain_core.messages import HumanMessage

            response = llm.invoke([HumanMessage(content=prompt_text)])
            content = getattr(response, "content", "") or ""
        except Exception as e:
            logger.warning("SkillMatcher: LLM invoke failed: %s", e)
            return []

        # Parse JSON
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


# ───────────────────── Default fallback prompt ─────────────────────

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
    """HARNESS_PROMPTS fallback callable. Business can override by registering a same-named prompt."""
    return DEFAULT_PROMPT_TEMPLATE.format(query=query, skills_json=skills_json)


def ensure_default_prompt_registered(prompt_name: str = DEFAULT_PROMPT_NAME) -> None:
    """Register the default skill match prompt to HARNESS_PROMPTS (idempotent).

    SkillOrchestrator.match_and_augment() calls this automatically; business can also call it once manually
    and then override with its own version via ``HARNESS_PROMPTS.register()``.
    """
    from agent_kit.harness.prompt_registry import HARNESS_PROMPTS

    # If a same-named one is already registered, don't override (business may have registered a Langfuse version)
    if prompt_name in HARNESS_PROMPTS._specs:  # type: ignore[attr-defined]
        return
    HARNESS_PROMPTS.register(prompt_name, fallback_callable=_default_prompt_fallback)


# ───────────────────── JSON parsing ─────────────────────

def _parse_response(content: str) -> list[MatchResult]:
    """LLM output → list of MatchResult. Tolerates markdown code blocks, single objects, invalid items."""
    if not content:
        return []
    cleaned = content.strip()
    # Strip markdown code block wrapping
    if cleaned.startswith("```"):
        # Remove the first line ``` or ```json
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
