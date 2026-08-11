"""agent_kit.skills: a progressive-disclosure skill system following the Anthropic SKILL.md spec.

PR1 scope:
- ``SkillManifest`` / ``MatchResult`` / ``SkillMatchRequest`` data models
- ``SkillRegistry``: scan directories + parse frontmatter
- ``SkillLoader``: load markdown body on demand
- ``PromptOnlyAdapter``: splice the body into the system prompt
- ``SkillOrchestrator``: one-stop entry point (explicit skill_ids version)

PR2 scope (added):
- ``SkillMatcher``: LLM matching based on HARNESS_ROUTER + HARNESS_PROMPTS
- ``Matcher`` Protocol: business can inject a custom matcher
- ``SkillOrchestrator.match_and_augment(query, base_prompt)``
- ``AgentRuntime.skills_dir()`` hook (added in runtimes/base.py)

PR3 will add:
- ``InProcessAdapter``: ``module:func`` → LangChain Tool
"""
from agent_kit.skills.adapters import InProcessAdapter, PromptOnlyAdapter
from agent_kit.skills.loader import SkillLoader
from agent_kit.skills.matcher import (
    DEFAULT_PROMPT_NAME,
    DEFAULT_TASK_TYPE,
    Matcher,
    SkillMatcher,
    ensure_default_prompt_registered,
)
from agent_kit.skills.models import (
    EntryPoint,
    EntryPointKind,
    IOSchema,
    MatchResult,
    SkillManifest,
    SkillMatchRequest,
    SkillMode,
)
from agent_kit.skills.orchestrator import SkillOrchestrator
from agent_kit.skills.registry import SkillRegistry, extract_body

__all__ = [
    # models
    "SkillManifest",
    "MatchResult",
    "SkillMatchRequest",
    "EntryPoint",
    "EntryPointKind",
    "IOSchema",
    "SkillMode",
    # components
    "SkillRegistry",
    "SkillLoader",
    "PromptOnlyAdapter",
    "InProcessAdapter",
    "SkillOrchestrator",
    "SkillMatcher",
    "Matcher",
    # constants
    "DEFAULT_TASK_TYPE",
    "DEFAULT_PROMPT_NAME",
    # helpers
    "extract_body",
    "ensure_default_prompt_registered",
]
