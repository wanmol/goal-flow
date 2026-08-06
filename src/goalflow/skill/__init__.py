"""
Skill system: progressive disclosure of skill content into system prompts.

Usage:
    from goalflow.skill import SkillOrchestrator

    orchestrator = SkillOrchestrator.create_default()
    system_prompt = orchestrator.build_prompt(
        query="上海今天天气怎么样",
        base_prompt="你是一个智能助手...",
    )
"""

from goalflow.skill.models import MatchResult, SkillContent, SkillMatchRequest, SkillMetadata
from goalflow.skill.registry import SkillRegistry
from goalflow.skill.matcher import SkillMatcher
from goalflow.skill.loader import SkillLoader
from goalflow.skill.prompt_builder import SystemPromptBuilder
from goalflow.skill.orchestrator import SkillOrchestrator

__all__ = [
    "SkillMetadata",
    "MatchResult",
    "SkillContent",
    "SkillMatchRequest",
    "SkillRegistry",
    "SkillMatcher",
    "SkillLoader",
    "SystemPromptBuilder",
    "SkillOrchestrator",
]
