"""agent_kit.runtimes: unified runtimes for different Agent shapes.

Provides three mainstream Agent shapes:
- DeepAgentRuntime: built on deepagents.create_deep_agent, with built-in planning/subagents/memory/HITL
- CreateAgentRuntime: built on langchain.agents.create_agent, minimal tool-calling
- StateGraphRuntime: a manual StateGraph, fully custom state machine
"""
from agent_kit.runtimes.base import AgentRuntime, AgentResult, classify_error
from agent_kit.runtimes.deep_agent import DeepAgentRuntime
from agent_kit.runtimes.create_agent import CreateAgentRuntime
from agent_kit.runtimes.state_graph import StateGraphRuntime

__all__ = [
    "AgentRuntime",
    "AgentResult",
    "DeepAgentRuntime",
    "CreateAgentRuntime",
    "StateGraphRuntime",
    "classify_error",
]
