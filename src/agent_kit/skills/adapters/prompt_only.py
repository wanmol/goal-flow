"""PromptOnlyAdapter: splice the SKILL.md body into the system prompt.

Output format (compatible with the host repo's SystemPromptBuilder, for smooth migration)::

    ## 当前激活的技能详情

    ### weather_query (v1.0.0)
    <full body>

    ### product_search (v1.0.0)
    <full body>
"""
from __future__ import annotations

from typing import Iterable

from agent_kit.skills.models import SkillManifest


class PromptOnlyAdapter:
    """Stateless adapter; all methods are pure functions (for easy unit testing)."""

    SECTION_HEADER = "## 当前激活的技能详情"

    @classmethod
    def render(cls, manifests: Iterable[SkillManifest]) -> str:
        """Splice the bodies of several manifests into a prompt fragment. Manifests with a None body are skipped."""
        sections: list[str] = []
        for m in manifests:
            if not m.body:
                continue
            sections.append(f"### {m.name} (v{m.version})\n{m.body}")
        if not sections:
            return ""
        return cls.SECTION_HEADER + "\n\n" + "\n\n".join(sections)

    @classmethod
    def append_to(cls, base_prompt: str, manifests: Iterable[SkillManifest]) -> str:
        """Append the skill fragment after base_prompt; return unchanged when there are no skills."""
        snippet = cls.render(manifests)
        if not snippet:
            return base_prompt
        if not base_prompt:
            return snippet
        return base_prompt.rstrip() + "\n\n" + snippet
