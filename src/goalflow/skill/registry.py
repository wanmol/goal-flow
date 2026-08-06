"""
Skill registry: scans skills/ subdirectories for SKILL.md, parses YAML frontmatter, builds metadata index.

Directory structure:
    skills/
    ├── weather_query/
    │   ├── SKILL.md          (required)
    │   └── scripts/          (optional)
    │       └── weather_api.py
    └── product_search/
        ├── SKILL.md
        └── scripts/
"""

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from goalflow.config import get_logger
from goalflow.skill.models import SkillMetadata

logger = get_logger(__name__)

SKILL_FILENAME = "SKILL.md"


class SkillRegistry:
    """Scans skill subdirectories and indexes SKILL.md metadata."""

    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir:
            self._skills_dir = Path(skills_dir)
        else:
            project_root = Path(__file__).resolve().parent.parent
            self._skills_dir = project_root / "skills"

        self._metadata_cache: Dict[str, SkillMetadata] = {}
        self._file_mtimes: Dict[str, float] = {}

        self.scan()

    def scan(self) -> int:
        """Scan skills directory for subdirectories containing SKILL.md. Returns count loaded."""
        self._metadata_cache.clear()
        self._file_mtimes.clear()

        if not self._skills_dir.exists():
            logger.warning("skills directory not found", path=str(self._skills_dir))
            return 0

        count = 0
        for sub_dir in sorted(self._skills_dir.iterdir()):
            if not sub_dir.is_dir():
                continue

            skill_file = sub_dir / SKILL_FILENAME
            if not skill_file.exists():
                logger.warning("skill subdirectory missing SKILL.md", path=str(sub_dir))
                continue

            metadata = self._parse_frontmatter(skill_file, sub_dir)
            if metadata:
                self._metadata_cache[metadata.skill_id] = metadata
                self._file_mtimes[str(skill_file)] = skill_file.stat().st_mtime
                count += 1

        logger.info("skill registry scan complete", count=count)
        return count

    def _parse_frontmatter(self, file_path: Path, skill_dir: Path) -> Optional[SkillMetadata]:
        """Parse YAML frontmatter from a SKILL.md file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("failed to read skill file", path=str(file_path), error=str(e))
            return None

        stripped = content.strip()
        if not stripped.startswith("---"):
            logger.warning("skill file missing frontmatter", path=str(file_path))
            return None

        second_delim = stripped.find("---", 3)
        if second_delim == -1:
            logger.warning("skill file missing closing frontmatter delimiter", path=str(file_path))
            return None

        yaml_text = stripped[3:second_delim].strip()
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            logger.warning("skill file YAML parse error", path=str(file_path), error=str(e))
            return None

        if not isinstance(data, dict):
            logger.warning("skill file frontmatter is not a dict", path=str(file_path))
            return None

        if "name" not in data or "description" not in data:
            logger.warning("skill file missing required fields (name, description)", path=str(file_path))
            return None

        skill_id = skill_dir.name
        data["skill_id"] = skill_id
        data["file_path"] = str(file_path)
        data["skill_dir"] = str(skill_dir)

        # Check for scripts/ subdirectory
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists() and scripts_dir.is_dir():
            data["scripts_dir"] = str(scripts_dir)

        try:
            return SkillMetadata(**data)
        except Exception as e:
            logger.warning("skill metadata validation error", path=str(file_path), error=str(e))
            return None

    def get_all_metadata(self) -> List[SkillMetadata]:
        """Return metadata for all enabled skills."""
        return [m for m in self._metadata_cache.values() if m.enabled]

    def get_metadata(self, skill_id: str) -> Optional[SkillMetadata]:
        """Return metadata for a specific skill."""
        return self._metadata_cache.get(skill_id)

    def reload(self) -> int:
        """Check for file changes and reload modified/new skills. Returns count of changes."""
        if not self._skills_dir.exists():
            return 0

        # Collect current SKILL.md files from subdirectories
        current_files: Dict[str, Path] = {}
        for sub_dir in self._skills_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            skill_file = sub_dir / SKILL_FILENAME
            if skill_file.exists():
                current_files[str(skill_file)] = skill_file

        changes = 0

        # Detect deleted
        for cached_path in list(self._file_mtimes.keys()):
            if cached_path not in current_files:
                skill_id = Path(cached_path).parent.name
                self._metadata_cache.pop(skill_id, None)
                self._file_mtimes.pop(cached_path, None)
                changes += 1
                logger.info("skill removed", skill_id=skill_id)

        # Detect new or modified
        for file_str, file_path in current_files.items():
            mtime = file_path.stat().st_mtime
            if file_str not in self._file_mtimes or self._file_mtimes[file_str] != mtime:
                metadata = self._parse_frontmatter(file_path, file_path.parent)
                if metadata:
                    self._metadata_cache[metadata.skill_id] = metadata
                    self._file_mtimes[file_str] = mtime
                    changes += 1

        if changes:
            logger.info("skill registry reloaded", changes=changes)
        return changes

    def has_changes(self) -> bool:
        """Quick check if any SKILL.md files were added/modified/deleted since last scan."""
        if not self._skills_dir.exists():
            return bool(self._metadata_cache)

        current_files = set()
        for sub_dir in self._skills_dir.iterdir():
            if not sub_dir.is_dir():
                continue
            skill_file = sub_dir / SKILL_FILENAME
            if skill_file.exists():
                current_files.add(str(skill_file))

        if current_files != set(self._file_mtimes.keys()):
            return True

        for file_str in current_files:
            file_path = Path(file_str)
            if file_path.stat().st_mtime != self._file_mtimes.get(file_str, 0):
                return True

        return False
