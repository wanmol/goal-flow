"""Data models for agent_kit.skills.

Design principles:
- Compatible with the SKILL.md frontmatter field set of the Anthropic Agent Skills spec
  (name / description / version required; all other fields optional)
- A **strict superset** of the field set of the host repo's ``skill/models.py::SkillMetadata``,
  so existing ``skills/*/SKILL.md`` files load in agent_kit without changing a single line
- Reserves the ``mode`` / ``entry_point`` / ``io_schema`` / ``scopes`` fields for PR3's executable skill;
  PR1 does not really consume them yet, but can already parse them from frontmatter
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


SkillMode = Literal["prompt_only", "executable", "hybrid"]
EntryPointKind = Literal["in_process", "mcp", "http", "cli"]


class IOSchema(BaseModel):
    """Input/output JSON Schema references. Only really consumed in PR3."""

    input: Optional[str] = None   # path relative to skill_dir, e.g. "schema/input.json"
    output: Optional[str] = None


class EntryPoint(BaseModel):
    """Entry point for an executable skill. Only really consumed in PR3 / PR4."""

    kind: EntryPointKind = "in_process"
    target: str = ""
    """Meaning varies by kind:

    - ``in_process``: ``module.path:function_name``
    - ``mcp``: ``server_uri:tool_name``
    - ``http``: full URL
    - ``cli``: shell command
    """
    tool_name: Optional[str] = None
    """Added in PR3: the tool name exposed by the LangChain Tool; defaults to manifest.skill_id.

    Must be a LangChain-compatible ASCII identifier ([a-zA-Z0-9_-]).
    """


class SkillManifest(BaseModel):
    """The parse product of SKILL.md.

    PR1 stage:
    - Parsed and populated from frontmatter by ``SkillRegistry``
    - The body field is populated after ``SkillLoader.load_body()`` (progressive disclosure)
    """

    # ── Anthropic SKILL.md required ────────────────────────
    name: str
    description: str

    # ── Common metadata (compatible with the host repo's skill/models.py) ──
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    enabled: bool = True

    # ── Reserved for PR3+ ──────────────────────────────────
    mode: SkillMode = "prompt_only"
    entry_point: Optional[EntryPoint] = None
    io_schema: Optional[IOSchema] = None
    scopes: list[str] = Field(default_factory=list)

    # ── Registration-stage internal fields (populated by Registry) ─────────────
    skill_id: str = ""
    file_path: str = ""
    skill_dir: str = ""
    scripts_dir: Optional[str] = None

    # ── Loading-stage internal fields (populated by Loader) ──────────────
    body: Optional[str] = None


class MatchResult(BaseModel):
    """SkillMatcher output (only really produced in PR2; defined early in PR1 to stabilize the API)."""

    skill_id: str
    skill_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class SkillMatchRequest(BaseModel):
    """SkillMatcher input (only really consumed in PR2)."""

    query: str
    top_k: int = 3
    threshold: float = 0.3
