"""SkillLoader: load the SKILL.md markdown body on demand (progressive disclosure, stage two).

Why the body is not read at the Registry stage:
- When there are many skills, loading all bodies slows startup and consumes memory
- In most business scenarios, a single session only triggers a few skills; loading on demand is more reasonable
- Consistent with the progressive disclosure model of the Anthropic Agent Skills spec
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from agent_kit.skills.models import SkillManifest
from agent_kit.skills.registry import SkillRegistry, extract_body

logger = logging.getLogger(__name__)


class SkillLoader:
    """Load the full body by skill_id.

    The loaded body is written back to the manifest.body cache; the next ``load_body()`` returns the cache directly.
    In unit tests/debugging, call ``invalidate(skill_id)`` to clear the cache.
    """

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def load_body(self, skill_id: str) -> Optional[str]:
        """Return the skill's markdown body; return None if missing."""
        manifest = self._registry.get(skill_id)
        if manifest is None:
            return None
        if manifest.body is not None:
            return manifest.body
        try:
            text = Path(manifest.file_path).read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("SkillLoader: read failed %s: %s", manifest.file_path, e)
            return None
        body = extract_body(text)
        manifest.body = body
        return body

    def load_many(self, skill_ids: list[str]) -> list[SkillManifest]:
        """Batch load; return the list of successfully loaded (body not None) manifests, in the same order as the input."""
        out: list[SkillManifest] = []
        for sid in skill_ids:
            body = self.load_body(sid)
            if body is None:
                continue
            manifest = self._registry.get(sid)
            if manifest is not None:
                out.append(manifest)
        return out

    def invalidate(self, skill_id: Optional[str] = None) -> None:
        """Clear the body cache. If skill_id is not passed, clear all."""
        if skill_id is None:
            for m in self._registry.all(enabled_only=False):
                m.body = None
            return
        manifest = self._registry.get(skill_id)
        if manifest is not None:
            manifest.body = None
