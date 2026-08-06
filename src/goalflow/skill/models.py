"""
Data models for the skill system.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class SkillMetadata(BaseModel):
    """Parsed from YAML frontmatter of a SKILL.md file."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = Field(default_factory=list)
    triggers: List[str] = Field(default_factory=list)
    enabled: bool = True
    file_path: str = ""
    skill_id: str = ""
    skill_dir: str = ""
    scripts_dir: Optional[str] = None


class MatchResult(BaseModel):
    """Output from SkillMatcher."""

    skill_id: str
    skill_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class SkillContent(BaseModel):
    """Full loaded skill: metadata + markdown body."""

    metadata: SkillMetadata
    content: str


class SkillMatchRequest(BaseModel):
    """Input to SkillMatcher."""

    query: str
    top_k: int = 1
    threshold: float = 0.3
