"""HarnessProfile: one-stop governance configuration for a task_type.

Consolidates the four tasks of "configure LLM + register Prompts + set skills_dir + tune
skill match thresholds" into a single register() call, avoiding scattered business startup
with 6+ separate ``HARNESS_ROUTER.configure`` / ``HARNESS_PROMPTS.register`` calls.

Design points:
- **Thin wrapper**: internally calls the existing ``HARNESS_ROUTER.configure`` + ``HARNESS_PROMPTS.register``,
  introducing no new storage; the old APIs keep working.
- **task_type is the primary bus**: a profile determines the main task_type + the sub task_type naming
  convention (``<task_type>.<sub_name>``) + the prompt naming convention (``<task_type>.<prompt_name>``).
- **Optional fields**: everything except task_type is optional; only configure the fields you care about.

Typical usage::

    HARNESS_PROFILES.register(
        "guided_clarification",
        llm={"temperature": 0.0, "model": "qwen-plus"},
        sub_llms={
            "match_fit": {"temperature": 0.1, "streaming": False},
            "extract": {"temperature": 0.0},
        },
        prompts={
            "system_clarify": _fallback_clarify,
            "system_commercial": _fallback_commercial,
        },
        skills_dir="./skills/guided_clarification",
    )

    # Runtime / business reads:
    profile = HARNESS_PROFILES.get("guided_clarification")
    profile.task_type           # "guided_clarification"
    profile.skills_dir          # "./skills/..."
    profile.skill_match_top_k   # 3
    profile.sub_task_type("match_fit")  # "guided_clarification.match_fit"
    profile.prompt_name("system_clarify")  # "guided_clarification.system_clarify"
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class HarnessProfile:
    """A governance configuration snapshot for a single task_type."""

    task_type: str
    llm: dict = field(default_factory=dict)
    sub_llms: dict[str, dict] = field(default_factory=dict)
    prompts: dict[str, Callable[..., str]] = field(default_factory=dict)
    skills_dir: Optional[str] = None
    skill_match_top_k: int = 3
    skill_match_threshold: float = 0.3
    extra: dict = field(default_factory=dict)

    def sub_task_type(self, name: str) -> str:
        """Sub task_type naming convention: <task_type>.<name>."""
        return f"{self.task_type}.{name}"

    def prompt_name(self, name: str) -> str:
        """Prompt naming convention: <task_type>.<name>."""
        return f"{self.task_type}.{name}"


class ProfileRegistry:
    """Global ProfileRegistry singleton (``HARNESS_PROFILES``)."""

    def __init__(self) -> None:
        self._profiles: dict[str, HarnessProfile] = {}
        self._lock = threading.RLock()

    def register(
        self,
        task_type: str,
        *,
        llm: Optional[dict] = None,
        sub_llms: Optional[dict[str, dict]] = None,
        prompts: Optional[dict[str, Callable[..., str]]] = None,
        skills_dir: Optional[str] = None,
        skill_match_top_k: int = 3,
        skill_match_threshold: float = 0.3,
        **extra,
    ) -> HarnessProfile:
        """Register the complete governance configuration for a task_type in one call.

        Internally fans out to ``HARNESS_ROUTER.configure`` and ``HARNESS_PROMPTS.register``.
        Re-registering the same task_type overwrites it.

        :param llm: LLM config for the main task_type, e.g. ``{"provider": "qwen", "model": "qwen-plus", "temperature": 0.0}``
        :param sub_llms: sub task_type config; key is the sub name (without the task_type prefix), value is an LLM config dict
        :param prompts: prompt name -> fallback callable; the full prompt name becomes ``<task_type>.<name>``
        :param skills_dir: skill root directory (business nodes can read it via profile.skills_dir)
        :param skill_match_top_k / threshold: skill match parameters (business nodes can read them via profile)
        :param extra: business-custom fields, stored in profile.extra
        """
        from agent_kit.harness.model_router import HARNESS_ROUTER
        from agent_kit.harness.prompt_registry import HARNESS_PROMPTS

        profile = HarnessProfile(
            task_type=task_type,
            llm=dict(llm or {}),
            sub_llms={k: dict(v) for k, v in (sub_llms or {}).items()},
            prompts=dict(prompts or {}),
            skills_dir=skills_dir,
            skill_match_top_k=skill_match_top_k,
            skill_match_threshold=skill_match_threshold,
            extra=dict(extra),
        )

        if profile.llm:
            HARNESS_ROUTER.configure(task_type, **profile.llm)
        for sub_name, sub_cfg in profile.sub_llms.items():
            HARNESS_ROUTER.configure(profile.sub_task_type(sub_name), **sub_cfg)
        for prompt_short_name, fallback_callable in profile.prompts.items():
            HARNESS_PROMPTS.register(
                name=profile.prompt_name(prompt_short_name),
                fallback_callable=fallback_callable,
            )

        with self._lock:
            self._profiles[task_type] = profile
        logger.info(
            f"HARNESS_PROFILES: registered task_type={task_type!r} "
            f"(sub_llms={list(profile.sub_llms.keys())}, "
            f"prompts={list(profile.prompts.keys())}, "
            f"skills_dir={'yes' if skills_dir else 'no'})"
        )
        return profile

    def get(self, task_type: str) -> Optional[HarnessProfile]:
        """Read a profile; returns None if not registered."""
        with self._lock:
            return self._profiles.get(task_type)

    def reset(self) -> None:
        """Clear all profile registrations. For unit tests only.

        Note: this method does not cascade-clear the side effects fanned out into
        ``HARNESS_ROUTER._configs`` / ``HARNESS_PROMPTS`` during ``register()``. To fully
        isolate between tests, do it yourself:

            HARNESS_PROFILES.reset()
            HARNESS_ROUTER.reset_all()
            HARNESS_PROMPTS.reset()
        """
        with self._lock:
            self._profiles.clear()


HARNESS_PROFILES = ProfileRegistry()
