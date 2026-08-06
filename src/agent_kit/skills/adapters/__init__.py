"""Skill 执行适配器。

每个 Adapter 把一种执行模式（prompt_only / in_process / mcp）翻译成统一的"产出"：
- PromptOnlyAdapter.render() / append_to() → str（拼进 system prompt 的片段）
- InProcessAdapter.materialize() → LangChain Tool
- MCPAdapter.materialize() → LangChain Tool 或 RemoteHandle（PR4）
"""
from agent_kit.skills.adapters.in_process import InProcessAdapter
from agent_kit.skills.adapters.prompt_only import PromptOnlyAdapter

__all__ = ["PromptOnlyAdapter", "InProcessAdapter"]
