"""agent_kit.skills 的数据模型。

设计原则：
- 与 Anthropic Agent Skills 规范的 SKILL.md frontmatter 字段集兼容
  （name / description / version 必备；其它字段都可选）
- 与宿主仓库内 ``skill/models.py::SkillMetadata`` 的字段集**严格超集**，
  现有 ``skills/*/SKILL.md`` 文件不改一行就能在 agent_kit 里加载
- 为 PR3 的 executable skill 预留 ``mode`` / ``entry_point`` / ``io_schema`` /
  ``scopes`` 字段；PR1 暂不真正消费，但已经能从 frontmatter 解析出来
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


SkillMode = Literal["prompt_only", "executable", "hybrid"]
EntryPointKind = Literal["in_process", "mcp", "http", "cli"]


class IOSchema(BaseModel):
    """输入/输出 JSON Schema 引用。PR3 才会真正消费。"""

    input: Optional[str] = None   # 相对于 skill_dir 的路径，如 "schema/input.json"
    output: Optional[str] = None


class EntryPoint(BaseModel):
    """可执行 skill 的入口点。PR3 / PR4 才会真正消费。"""

    kind: EntryPointKind = "in_process"
    target: str = ""
    """根据 kind 不同含义不同：

    - ``in_process``: ``module.path:function_name``
    - ``mcp``: ``server_uri:tool_name``
    - ``http``: 完整 URL
    - ``cli``: shell 命令
    """
    tool_name: Optional[str] = None
    """PR3 加入：LangChain Tool 暴露的工具名；缺省用 manifest.skill_id。

    必须是 LangChain 兼容的 ASCII 标识符（[a-zA-Z0-9_-]）。
    """


class SkillManifest(BaseModel):
    """SKILL.md 的解析产物。

    PR1 阶段：
    - 由 ``SkillRegistry`` 从 frontmatter 解析填充
    - body 字段在 ``SkillLoader.load_body()`` 后填充（渐进披露）
    """

    # ── Anthropic SKILL.md 必备 ────────────────────────
    name: str
    description: str

    # ── 通用元数据（与宿主仓库 skill/models.py 兼容） ──
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    enabled: bool = True

    # ── PR3+ 预留 ──────────────────────────────────────
    mode: SkillMode = "prompt_only"
    entry_point: Optional[EntryPoint] = None
    io_schema: Optional[IOSchema] = None
    scopes: list[str] = Field(default_factory=list)

    # ── 注册阶段内部字段（由 Registry 填充） ─────────────
    skill_id: str = ""
    file_path: str = ""
    skill_dir: str = ""
    scripts_dir: Optional[str] = None

    # ── 加载阶段内部字段（由 Loader 填充） ──────────────
    body: Optional[str] = None


class MatchResult(BaseModel):
    """SkillMatcher 输出（PR2 才真正产生；PR1 提前定义以稳定 API）。"""

    skill_id: str
    skill_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class SkillMatchRequest(BaseModel):
    """SkillMatcher 输入（PR2 才真正消费）。"""

    query: str
    top_k: int = 3
    threshold: float = 0.3
