"""
HarnessBacked mixin: lets any AgentRuntime subclass automatically hook into the Harness's Model Router + Profiles.

Usage::

    class MyAgent(HarnessBacked, DeepAgentRuntime[MyResult]):
        task_type = "requirement_collection"

    HARNESS_PROFILES.register(
        "requirement_collection",
        llm={"temperature": 0.1},
        skills_dir="./skills/req",
    )
    # Or the old API:
    HARNESS_ROUTER.register_llm_factory(LLM.create)
    HARNESS_ROUTER.configure("requirement_collection", temperature=0.1)
"""
from __future__ import annotations

from typing import Any, Optional


class HarnessBacked:
    """Lets AgentRuntime subclasses automatically get the LLM from ``HARNESS_ROUTER`` + automatically
    read the skill config from ``HARNESS_PROFILES``.

    Must set the class attribute ``task_type``.

    Automatic profile integration (P9-a):
        - Once the business registers via ``HARNESS_PROFILES.register(task_type, skills_dir=..., ...)``,
          this mixin's ``skills_dir()`` / ``skill_match_top_k()`` / ``skill_match_threshold()``
          automatically read from the profile
        - When a business subclass overrides these hooks, they take precedence **over** the profile (naturally via Python MRO)
        - When no profile is registered, behavior matches the base class default (skills_dir() returns None, skill is skipped)
    """

    task_type: str = ""

    def _get_llm(self):
        if getattr(self, "_llm", None) is not None:
            return self._llm

        if not self.task_type:
            raise RuntimeError(
                f"{type(self).__name__}: task_type is empty; "
                "HarnessBacked subclasses must set `task_type` class attribute "
                "to enable automatic LLM routing."
            )

        from agent_kit.harness.model_router import HARNESS_ROUTER

        llm = HARNESS_ROUTER.get(self.task_type)
        self._llm = llm
        return llm

    @property
    def profile(self):
        """Read the ``HarnessProfile`` for this task_type; returns None if not registered."""
        if not self.task_type:
            return None
        from agent_kit.harness.profiles import HARNESS_PROFILES

        return HARNESS_PROFILES.get(self.task_type)

    # ───── Skill config defaults: read from profile, subclass override takes precedence ────

    def skills_dir(self) -> Optional[str]:
        """skills root directory. Reads from ``HARNESS_PROFILES`` by default; None if not registered or the profile does not set it."""
        p = self.profile
        return p.skills_dir if p else None

    def skill_match_top_k(self) -> int:
        p = self.profile
        return p.skill_match_top_k if p else 3

    def skill_match_threshold(self) -> float:
        p = self.profile
        return p.skill_match_threshold if p else 0.3
