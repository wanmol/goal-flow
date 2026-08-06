"""
Skill loader: loads full content of matched skill files.
"""

from pathlib import Path
from typing import List, Optional

from goalflow.config import get_logger
from goalflow.skill.models import SkillContent, SkillMetadata
from goalflow.skill.registry import SkillRegistry

logger = get_logger(__name__)


class SkillLoader:
    """Loads the full markdown content of skill files on demand."""

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def load(self, skill_id: str) -> Optional[SkillContent]:
        """Load a skill's full content by ID. Returns None if not found."""
        metadata = self._registry.get_metadata(skill_id)
        if not metadata:
            logger.warning("skill not found in registry", skill_id=skill_id)
            return None

        body = self._extract_body(metadata.file_path)
        if body is None:
            return None

        return SkillContent(metadata=metadata, content=body)

    def load_multiple(self, skill_ids: List[str]) -> List[SkillContent]:
        """Load multiple skills by ID. Skips any that fail to load."""
        results = []
        for skill_id in skill_ids:
            content = self.load(skill_id)
            if content:
                results.append(content)
        return results

    def _extract_body(self, file_path: str) -> Optional[str]:
        """Read a skill file and return the content after the frontmatter."""
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("failed to read skill file", path=file_path, error=str(e))
            return None

        stripped = content.strip()
        if not stripped.startswith("---"):
            return stripped

        second_delim = stripped.find("---", 3)
        if second_delim == -1:
            return stripped

        body = stripped[second_delim + 3:].strip()
        return body
