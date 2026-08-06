"""SkillOrchestrator：串起 Registry / Loader / Matcher / Adapter 的入口。

PR1 范围（已完成）：
- ``load_skills(skill_ids)`` 显式按 ID 加载
- ``augment_prompt_with(base_prompt, skill_ids)`` 显式拼 prompt

PR2 范围（已加入）：
- ``match(query, top_k, threshold)`` LLM 匹配
- ``match_and_augment(query, base_prompt)`` 自动选 skill + 拼 prompt
- 注入自定义 matcher（实现 ``Matcher`` 协议）

典型用法（PR2 自动匹配版）::

    orch = SkillOrchestrator.create_default("./skills")
    augmented_prompt = orch.match_and_augment(
        query="上海今天天气怎么样",
        base_prompt="你是助手。",
    )
"""
from __future__ import annotations

import logging
from typing import Optional

from agent_kit.skills.adapters.in_process import InProcessAdapter
from agent_kit.skills.adapters.prompt_only import PromptOnlyAdapter
from agent_kit.skills.loader import SkillLoader
from agent_kit.skills.matcher import (
    Matcher,
    SkillMatcher,
    ensure_default_prompt_registered,
)
from agent_kit.skills.models import MatchResult, SkillManifest
from agent_kit.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillOrchestrator:
    """单 skills 根目录的协调器。多根目录场景下创建多个实例。"""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        loader: Optional[SkillLoader] = None,
        matcher: Optional[Matcher] = None,
        prompt_adapter: Optional[PromptOnlyAdapter] = None,
        in_process_adapter: Optional[InProcessAdapter] = None,
    ):
        self._registry = registry
        self._loader = loader or SkillLoader(registry)
        self._matcher: Matcher = matcher or SkillMatcher()
        self._prompt_adapter = prompt_adapter or PromptOnlyAdapter()
        self._in_process_adapter = in_process_adapter or InProcessAdapter()
        ensure_default_prompt_registered()

    # ───────────────── 工厂 ─────────────────

    @classmethod
    def create_default(
        cls,
        skills_dir: str,
        *,
        auto_discover: bool = True,
        matcher: Optional[Matcher] = None,
    ) -> "SkillOrchestrator":
        registry = SkillRegistry(skills_dir)
        if auto_discover:
            registry.discover()
        return cls(registry=registry, matcher=matcher)

    # ───────────────── 属性 ─────────────────

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    @property
    def matcher(self) -> Matcher:
        return self._matcher

    # ───────────────── 显式加载 (PR1) ─────────────────

    def load_skills(self, skill_ids: list[str]) -> list[SkillManifest]:
        """按 ID 加载 manifest（含 body）。未知/未启用/读失败的会被静默跳过。"""
        result: list[SkillManifest] = []
        for sid in skill_ids:
            manifest = self._registry.get(sid)
            if manifest is None or not manifest.enabled:
                continue
            body = self._loader.load_body(sid)
            if body is None:
                continue
            result.append(manifest)
        return result

    def augment_prompt_with(
        self,
        *,
        base_prompt: str,
        skill_ids: list[str],
    ) -> str:
        manifests = self.load_skills(skill_ids)
        return self._prompt_adapter.append_to(base_prompt, manifests)

    # ───────────────── 自动匹配 (PR2) ─────────────────

    def match(
        self,
        query: str,
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[MatchResult]:
        """按 query 匹配 skill。返回按 confidence 降序的 MatchResult 列表。"""
        manifests = self._registry.all(enabled_only=True)
        if not manifests:
            return []
        try:
            return self._matcher.match(
                query, manifests, top_k=top_k, threshold=threshold
            )
        except Exception as e:
            logger.warning("SkillOrchestrator.match failed: %s", e)
            return []

    def match_and_load(
        self,
        query: str,
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> tuple[list[MatchResult], list[SkillManifest]]:
        """匹配 + 加载 body。返回 (matches, manifests_with_body)。"""
        matches = self.match(query, top_k=top_k, threshold=threshold)
        if not matches:
            return [], []
        manifests = self.load_skills([m.skill_id for m in matches])
        return matches, manifests

    def match_and_augment(
        self,
        *,
        query: str,
        base_prompt: str,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> str:
        """一站式：query → 自动匹配 → 加载 body → 拼到 base_prompt。

        ``executable`` 模式的 skill 不会拼 body（它走 tool 路径）；
        ``prompt_only`` 和 ``hybrid`` 模式的 body 会拼进 prompt。
        """
        _, manifests = self.match_and_load(query, top_k=top_k, threshold=threshold)
        prompt_manifests = [m for m in manifests if m.mode in ("prompt_only", "hybrid")]
        return self._prompt_adapter.append_to(base_prompt, prompt_manifests)

    # ───────────────── 可执行 skill (PR3) ─────────────────

    def materialize_tools(self, manifests: list[SkillManifest]) -> list:
        """把 ``executable`` / ``hybrid`` 模式的 manifest 转成 LangChain Tool 列表。

        ``prompt_only`` 模式的 manifest 会被跳过（它们走 augment_prompt 路径）。
        单个 skill 失败（import 错 / 函数不存在）会被静默 skip + warn log，
        不影响其它 skill。
        """
        executable = [m for m in manifests if m.mode in ("executable", "hybrid")]
        if not executable:
            return []
        return self._in_process_adapter.materialize_many(executable)

    def match_and_materialize_tools(
        self,
        query: str,
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> tuple[list[SkillManifest], list]:
        """匹配 + 加载 + 编译 tools。返回 (manifests_with_body, langchain_tools)。

        AgentRuntime 在 PR3 里用这个方法一次性拿到 prompt 增强所需的 manifests
        和 tool 注入所需的 tools。
        """
        _, manifests = self.match_and_load(query, top_k=top_k, threshold=threshold)
        if not manifests:
            return [], []
        tools = self.materialize_tools(manifests)
        return manifests, tools

    def augment_prompt(self, base_prompt: str, manifests: list[SkillManifest]) -> str:
        """显式版本：把 prompt_only/hybrid 的 manifest 拼进 base_prompt。

        与 match_and_augment 的区别是：调用方已经持有 manifests，
        无需再跑匹配（避免和 ``match_and_materialize_tools`` 重复匹配）。
        """
        prompt_manifests = [m for m in manifests if m.mode in ("prompt_only", "hybrid")]
        return self._prompt_adapter.append_to(base_prompt, prompt_manifests)
