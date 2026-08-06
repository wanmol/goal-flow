"""
System prompt builder: composes system prompts with skill metadata and matched skill content.
"""

from typing import List, Optional

from goalflow.skill.models import SkillContent
from goalflow.skill.registry import SkillRegistry


class SystemPromptBuilder:
    """Builds system prompts with skill metadata summary and matched skill details."""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def build_metadata_summary(self) -> str:
        """Generate a compact summary of all enabled skills (always included in system prompt)."""
        metadata_list = self._registry.get_all_metadata()
        if not metadata_list:
            return ""

        lines = ["## 可用技能", "以下是你可以使用的技能列表："]
        for m in metadata_list:
            lines.append(f"- **{m.name}**: {m.description}")

        return "\n".join(lines)

    def build_skill_detail(self, skill_contents: List[SkillContent]) -> str:
        """Format matched skill full content for inclusion in system prompt."""
        if not skill_contents:
            return ""

        sections = ["## 当前激活的技能详情"]
        for sc in skill_contents:
            sections.append(f"\n### {sc.metadata.name} (v{sc.metadata.version})")
            sections.append(sc.content)

        return "\n".join(sections)

    def build_system_prompt(
        self,
        base_prompt: str,
        matched_skills: Optional[List[SkillContent]] = None,
    ) -> str:
        """Compose the full system prompt: base + matched skill details (no metadata summary)."""
        parts = [base_prompt]

        if matched_skills:
            skill_detail = self.build_skill_detail(matched_skills)
            if skill_detail:
                parts.append(skill_detail)

        return "\n\n".join(parts)
