"""SkillOrchestrator: the entry point that ties together Registry / Loader / Matcher / Adapter.

PR1 scope (done):
- ``load_skills(skill_ids)`` explicit load by ID
- ``augment_prompt_with(base_prompt, skill_ids)`` explicit prompt splicing

PR2 scope (added):
- ``match(query, top_k, threshold)`` LLM matching
- ``match_and_augment(query, base_prompt)`` auto-select skill + splice prompt
- Inject a custom matcher (implementing the ``Matcher`` protocol)

Typical usage (PR2 auto-matching version)::

    orch = SkillOrchestrator.create_default("./skills")
    augmented_prompt = orch.match_and_augment(
        query="What's the weather in Shanghai today",
        base_prompt="You are an assistant.",
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
    """Coordinator for a single skills root directory. Create multiple instances for multi-root scenarios."""

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

    # ───────────────── Factory ─────────────────

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

    # ───────────────── Properties ─────────────────

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    @property
    def matcher(self) -> Matcher:
        return self._matcher

    # ───────────────── Explicit loading (PR1) ─────────────────

    def load_skills(self, skill_ids: list[str]) -> list[SkillManifest]:
        """Load manifests (including body) by ID. Unknown/disabled/read-failed ones are silently skipped."""
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

    # ───────────────── Auto matching (PR2) ─────────────────

    def match(
        self,
        query: str,
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[MatchResult]:
        """Match skills by query. Return a list of MatchResult sorted by confidence descending."""
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
        """Match + load body. Return (matches, manifests_with_body)."""
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
        """One-stop: query → auto match → load body → splice into base_prompt.

        Skills in ``executable`` mode do not splice their body (they go the tool path);
        the body of ``prompt_only`` and ``hybrid`` mode skills is spliced into the prompt.
        """
        _, manifests = self.match_and_load(query, top_k=top_k, threshold=threshold)
        prompt_manifests = [m for m in manifests if m.mode in ("prompt_only", "hybrid")]
        return self._prompt_adapter.append_to(base_prompt, prompt_manifests)

    # ───────────────── Executable skill (PR3) ─────────────────

    def materialize_tools(self, manifests: list[SkillManifest]) -> list:
        """Convert ``executable`` / ``hybrid`` mode manifests into a list of LangChain Tools.

        ``prompt_only`` mode manifests are skipped (they go the augment_prompt path).
        A single skill failure (import error / function missing) is silently skipped + warn logged,
        without affecting other skills.
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
        """Match + load + compile tools. Return (manifests_with_body, langchain_tools).

        In PR3, AgentRuntime uses this method to obtain in one shot both the manifests needed for prompt
        augmentation and the tools needed for tool injection.
        """
        _, manifests = self.match_and_load(query, top_k=top_k, threshold=threshold)
        if not manifests:
            return [], []
        tools = self.materialize_tools(manifests)
        return manifests, tools

    def augment_prompt(self, base_prompt: str, manifests: list[SkillManifest]) -> str:
        """Explicit version: splice prompt_only/hybrid manifests into base_prompt.

        The difference from match_and_augment is that the caller already holds the manifests,
        so no need to run matching again (avoids duplicate matching with ``match_and_materialize_tools``).
        """
        prompt_manifests = [m for m in manifests if m.mode in ("prompt_only", "hybrid")]
        return self._prompt_adapter.append_to(base_prompt, prompt_manifests)
