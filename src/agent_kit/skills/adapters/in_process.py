"""InProcessAdapter: convert SkillManifest.entry_point (kind=in_process) into a LangChain Tool.

Conventions:
- ``entry_point.target`` format: ``"module.path:function_name"``
  e.g. ``"my_skill_pkg.weather:get_weather"``
- Any function signature; LangChain ``@tool`` auto-generates the schema from signature + type annotations + docstring
- tool name priority:
    1. ``entry_point.tool_name`` (optional field, added in PR3)
    2. ``manifest.skill_id`` (kebab-case directory name, always ASCII, LangChain-compatible)
- tool description:
    1. function docstring (LangChain prefers this)
    2. fall back to ``manifest.description``

Error handling:
- import failure / function missing / non-callable / missing docstring → silent skip + warn log
- one skill's error does not affect other skills
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

from agent_kit.skills.models import SkillManifest

logger = logging.getLogger(__name__)


class InProcessAdapter:
    """Stateless adapter; purely functional API."""

    @classmethod
    def materialize(cls, manifest: SkillManifest) -> Optional[Any]:
        """Convert a single manifest into a LangChain Tool; return None on failure."""
        ep = manifest.entry_point
        if ep is None:
            logger.warning(
                "InProcessAdapter: skill %r has no entry_point; skipping",
                manifest.skill_id,
            )
            return None
        if ep.kind != "in_process":
            logger.warning(
                "InProcessAdapter: skill %r entry_point.kind=%r is not in_process; skipping",
                manifest.skill_id,
                ep.kind,
            )
            return None

        fn = _resolve_target(ep.target, manifest.skill_id)
        if fn is None:
            return None

        # Try to get tool_name; if EntryPoint doesn't declare one, use skill_id
        tool_name = getattr(ep, "tool_name", None) or manifest.skill_id

        # Wrap with LangChain @tool
        try:
            from langchain_core.tools import tool as lc_tool

            # If the function has no docstring, fall back to manifest.description (LangChain requires description)
            if not fn.__doc__:
                fn.__doc__ = manifest.description or f"Skill: {manifest.name}"

            return lc_tool(tool_name)(fn)
        except Exception as e:
            logger.warning(
                "InProcessAdapter: failed to wrap skill %r as LangChain tool: %s",
                manifest.skill_id,
                e,
            )
            return None

    @classmethod
    def materialize_many(cls, manifests: list[SkillManifest]) -> list[Any]:
        """Batch; only returns tools that materialized successfully."""
        tools = []
        for m in manifests:
            t = cls.materialize(m)
            if t is not None:
                tools.append(t)
        return tools


def _resolve_target(target: str, skill_id: str):
    """``"pkg.mod:func"`` → callable object. Return None on failure."""
    if not target or ":" not in target:
        logger.warning(
            "InProcessAdapter: skill %r target=%r missing ':' separator (expect 'module:func')",
            skill_id,
            target,
        )
        return None
    module_path, _, func_name = target.partition(":")
    module_path = module_path.strip()
    func_name = func_name.strip()
    if not module_path or not func_name:
        logger.warning(
            "InProcessAdapter: skill %r target=%r has empty module/func part",
            skill_id,
            target,
        )
        return None

    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        logger.warning(
            "InProcessAdapter: skill %r failed to import %r: %s",
            skill_id,
            module_path,
            e,
        )
        return None

    fn = getattr(module, func_name, None)
    if fn is None:
        logger.warning(
            "InProcessAdapter: skill %r function %r not found in module %r",
            skill_id,
            func_name,
            module_path,
        )
        return None
    if not callable(fn):
        logger.warning(
            "InProcessAdapter: skill %r %s.%s is not callable",
            skill_id,
            module_path,
            func_name,
        )
        return None
    return fn
