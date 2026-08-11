"""SkillRegistry: scan the skills root directory, parse SKILL.md frontmatter, and build an index (progressive disclosure, stage one).

The agreed directory structure (consistent with the Anthropic Agent Skills spec)::

    skills/
    ├── weather_query/
    │   ├── SKILL.md          (required)
    │   ├── scripts/          (optional)
    │   │   └── weather_api.py
    │   └── schema/           (optional)
    │       └── input.json
    └── product_search/
        └── SKILL.md

Progressive disclosure:
- ``discover()`` only reads YAML frontmatter, not the markdown body
- the markdown body is loaded on demand by ``SkillLoader.load_body(skill_id)``
- multiple discover() calls are idempotent; ``reload()`` does incremental updates based on mtime
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from agent_kit.skills.models import SkillManifest

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"


class SkillRegistry:
    """SKILL.md index. Not thread-safe; when sharing across multiple Runtimes in the same process, the caller should lock or use a global singleton."""

    def __init__(self, skills_dir: str | Path):
        self._skills_dir = Path(skills_dir).expanduser().resolve()
        self._manifests: dict[str, SkillManifest] = {}
        self._mtimes: dict[str, float] = {}

    # ───────────────── public API ─────────────────

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    def discover(self) -> int:
        """Full scan; return the number of skills successfully loaded."""
        self._manifests.clear()
        self._mtimes.clear()

        if not self._skills_dir.exists():
            logger.warning("SkillRegistry: skills_dir not found: %s", self._skills_dir)
            return 0

        count = 0
        for sub in sorted(self._skills_dir.iterdir()):
            if not sub.is_dir():
                continue
            skill_file = sub / SKILL_FILENAME
            if not skill_file.exists():
                continue
            manifest = self._parse(skill_file, sub)
            if manifest is None:
                continue
            self._manifests[manifest.skill_id] = manifest
            self._mtimes[str(skill_file)] = skill_file.stat().st_mtime
            count += 1
        logger.info("SkillRegistry: discovered %d skills under %s", count, self._skills_dir)
        return count

    def get(self, skill_id: str) -> Optional[SkillManifest]:
        return self._manifests.get(skill_id)

    def all(self, *, enabled_only: bool = True) -> list[SkillManifest]:
        manifests = list(self._manifests.values())
        if enabled_only:
            manifests = [m for m in manifests if m.enabled]
        return manifests

    def reload(self) -> int:
        """Incremental scan based on mtime; return the number of changes this time (additions + modifications + deletions)."""
        if not self._skills_dir.exists():
            n = len(self._manifests)
            self._manifests.clear()
            self._mtimes.clear()
            return n

        current: dict[str, Path] = {}
        for sub in self._skills_dir.iterdir():
            if not sub.is_dir():
                continue
            f = sub / SKILL_FILENAME
            if f.exists():
                current[str(f)] = f

        changes = 0
        # Deletions
        for path in list(self._mtimes.keys()):
            if path not in current:
                skill_id = Path(path).parent.name
                self._manifests.pop(skill_id, None)
                self._mtimes.pop(path, None)
                changes += 1

        # Additions / modifications
        for path_str, path in current.items():
            mtime = path.stat().st_mtime
            if self._mtimes.get(path_str) == mtime:
                continue
            manifest = self._parse(path, path.parent)
            if manifest is None:
                continue
            self._manifests[manifest.skill_id] = manifest
            self._mtimes[path_str] = mtime
            changes += 1
        return changes

    def has_changes(self) -> bool:
        """Quickly determine whether a reload is needed (without actually parsing)."""
        if not self._skills_dir.exists():
            return bool(self._manifests)
        current = set()
        for sub in self._skills_dir.iterdir():
            if not sub.is_dir():
                continue
            f = sub / SKILL_FILENAME
            if f.exists():
                current.add(str(f))
        if current != set(self._mtimes.keys()):
            return True
        for p in current:
            if Path(p).stat().st_mtime != self._mtimes.get(p):
                return True
        return False

    # ───────────────── internals ─────────────────

    def _parse(self, file_path: Path, skill_dir: Path) -> Optional[SkillManifest]:
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("SkillRegistry: read failed %s: %s", file_path, e)
            return None

        frontmatter = _extract_frontmatter(text)
        if frontmatter is None:
            logger.warning("SkillRegistry: missing/invalid frontmatter: %s", file_path)
            return None

        try:
            import yaml
        except ImportError:
            logger.error(
                "SkillRegistry: PyYAML not installed; "
                "install with `pip install agent_kit[skills]` or `pip install PyYAML`"
            )
            return None

        try:
            data = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as e:
            logger.warning("SkillRegistry: YAML parse error %s: %s", file_path, e)
            return None

        if not isinstance(data, dict):
            logger.warning("SkillRegistry: frontmatter is not a mapping: %s", file_path)
            return None
        if "name" not in data or "description" not in data:
            logger.warning(
                "SkillRegistry: frontmatter missing required name/description: %s", file_path
            )
            return None

        data["skill_id"] = skill_dir.name
        data["file_path"] = str(file_path)
        data["skill_dir"] = str(skill_dir)
        scripts = skill_dir / "scripts"
        if scripts.exists() and scripts.is_dir():
            data["scripts_dir"] = str(scripts)

        try:
            return SkillManifest(**data)
        except Exception as e:
            logger.warning("SkillRegistry: manifest validation failed %s: %s", file_path, e)
            return None


# ───────────────── helpers ─────────────────

def _extract_frontmatter(text: str) -> Optional[str]:
    """Return the YAML frontmatter text (without the ``---`` separators); return None if there is no frontmatter."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    end = stripped.find("---", 3)
    if end == -1:
        return None
    return stripped[3:end].strip()


def extract_body(text: str) -> str:
    """Extract the markdown body (without frontmatter) from the full SKILL.md text."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return stripped
    end = stripped.find("---", 3)
    if end == -1:
        return stripped
    return stripped[end + 3:].lstrip()
