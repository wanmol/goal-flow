"""PromptOnlyAdapter：把 SKILL.md body 拼进 system prompt。

输出格式（与宿主仓库 SystemPromptBuilder 兼容，便于平滑迁移）::

    ## 当前激活的技能详情

    ### weather_query (v1.0.0)
    <body 全文>

    ### product_search (v1.0.0)
    <body 全文>
"""
from __future__ import annotations

from typing import Iterable

from agent_kit.skills.models import SkillManifest


class PromptOnlyAdapter:
    """无状态适配器；所有方法都是纯函数（便于单测）。"""

    SECTION_HEADER = "## 当前激活的技能详情"

    @classmethod
    def render(cls, manifests: Iterable[SkillManifest]) -> str:
        """把若干 manifest 的 body 拼成 prompt 片段。body 为 None 的会被跳过。"""
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
        """在 base_prompt 之后追加 skill 片段；无 skill 时原样返回。"""
        snippet = cls.render(manifests)
        if not snippet:
            return base_prompt
        if not base_prompt:
            return snippet
        return base_prompt.rstrip() + "\n\n" + snippet
