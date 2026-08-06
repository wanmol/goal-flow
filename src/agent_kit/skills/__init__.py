"""agent_kit.skills：Anthropic SKILL.md 规范的渐进披露式 skill 系统。

PR1 范围：
- ``SkillManifest`` / ``MatchResult`` / ``SkillMatchRequest`` 数据模型
- ``SkillRegistry``：扫盘 + 解析 frontmatter
- ``SkillLoader``：按需加载 markdown body
- ``PromptOnlyAdapter``：把 body 拼进 system prompt
- ``SkillOrchestrator``：一站式入口（显式指定 skill_ids 版）

PR2 范围（已加入）：
- ``SkillMatcher``：基于 HARNESS_ROUTER + HARNESS_PROMPTS 的 LLM 匹配
- ``Matcher`` Protocol：业务可注入自定义 matcher
- ``SkillOrchestrator.match_and_augment(query, base_prompt)``
- ``AgentRuntime.skills_dir()`` 钩子（在 runtimes/base.py 里加）

PR3 将加入：
- ``InProcessAdapter``：``module:func`` → LangChain Tool
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
