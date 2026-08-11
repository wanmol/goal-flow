"""Skill execution adapters.

Each Adapter translates one execution mode (prompt_only / in_process / mcp) into a unified "output":
- PromptOnlyAdapter.render() / append_to() → str (a fragment spliced into the system prompt)
- InProcessAdapter.materialize() → LangChain Tool
- MCPAdapter.materialize() → LangChain Tool or RemoteHandle (PR4)
"""
from agent_kit.skills.adapters.in_process import InProcessAdapter
from agent_kit.skills.adapters.prompt_only import PromptOnlyAdapter

__all__ = ["PromptOnlyAdapter", "InProcessAdapter"]
