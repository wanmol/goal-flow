"""SkillLoader：按需加载 SKILL.md 的 markdown body（渐进披露第二阶段）。

不在 Registry 阶段读 body 的原因：
- 当 skills 数量较多时，全量加载 body 会拖慢启动并占用内存
- 大多数业务场景下，单次会话只触发少量 skill；按需读更合理
- 与 Anthropic Agent Skills 规范的 progressive disclosure 模型一致
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from agent_kit.skills.models import SkillManifest
from agent_kit.skills.registry import SkillRegistry, extract_body

logger = logging.getLogger(__name__)


class SkillLoader:
    """按 skill_id 加载完整 body。

    body 加载结果会写回 manifest.body 缓存；下次 ``load_body()`` 直接返回缓存。
    单测/调试时调 ``invalidate(skill_id)`` 清缓存。
    """

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def load_body(self, skill_id: str) -> Optional[str]:
        """返回 skill 的 markdown body；缺失返回 None。"""
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
        """批量加载；返回成功加载（body 非 None）的 manifest 列表，顺序与入参一致。"""
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
        """清 body 缓存。不传 skill_id 清全部。"""
        if skill_id is None:
            for m in self._registry.all(enabled_only=False):
                m.body = None
            return
        manifest = self._registry.get(skill_id)
        if manifest is not None:
            manifest.body = None
