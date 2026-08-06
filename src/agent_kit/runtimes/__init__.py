"""agent_kit.runtimes：不同 Agent 形态的统一运行时。

提供三种主流 Agent 形态：
- DeepAgentRuntime：底层 deepagents.create_deep_agent，自带 planning/subagents/memory/HITL
- CreateAgentRuntime：底层 langchain.agents.create_agent，最小 tool-calling
- StateGraphRuntime：手动 StateGraph，完全自定义状态机
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
