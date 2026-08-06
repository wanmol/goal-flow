"""SkillRegistry：扫描 skills 根目录，解析 SKILL.md frontmatter，建立索引（渐进披露第一阶段）。

约定的目录结构（与 Anthropic Agent Skills 规范一致）::

    skills/
    ├── weather_query/
    │   ├── SKILL.md          (required)
    │   ├── scripts/          (optional)
    │   │   └── weather_api.py
    │   └── schema/           (optional)
    │       └── input.json
    └── product_search/
        └── SKILL.md

渐进披露：
- ``discover()`` 只读 YAML frontmatter，不读 markdown body
- markdown body 由 ``SkillLoader.load_body(skill_id)`` 按需加载
- 多次 discover() 是幂等的；``reload()`` 基于 mtime 增量更新
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from agent_kit.skills.models import SkillManifest

logger = logging.getLogger(__name__)

SKILL_FILENAME = "SKILL.md"


class SkillRegistry:
    """SKILL.md 索引。线程不安全；同进程多 Runtime 共享时由调用方加锁或用全局单例。"""

    def __init__(self, skills_dir: str | Path):
        self._skills_dir = Path(skills_dir).expanduser().resolve()
        self._manifests: dict[str, SkillManifest] = {}
        self._mtimes: dict[str, float] = {}

    # ───────────────── public API ─────────────────

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    def discover(self) -> int:
        """全量扫描；返回成功加载的 skill 数。"""
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
        """基于 mtime 增量扫描；返回本次变更数（新增 + 修改 + 删除）。"""
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
        # 删除
        for path in list(self._mtimes.keys()):
            if path not in current:
                skill_id = Path(path).parent.name
                self._manifests.pop(skill_id, None)
                self._mtimes.pop(path, None)
                changes += 1

        # 新增 / 修改
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
        """快速判断是否需要 reload（不真正解析）。"""
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
    """返回 YAML frontmatter 文本（不含 ``---`` 分隔符）；无 frontmatter 返回 None。"""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    end = stripped.find("---", 3)
    if end == -1:
        return None
    return stripped[3:end].strip()


def extract_body(text: str) -> str:
    """从 SKILL.md 全文里取出 markdown body（不含 frontmatter）。"""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return stripped
    end = stripped.find("---", 3)
    if end == -1:
        return stripped
    return stripped[end + 3:].lstrip()
