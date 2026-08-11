import logging
from typing import Any, Callable, Optional
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing_extensions import override
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage

from agent_kit.harness.middleware.agent_state import ContextAgentState

logger = logging.getLogger(__name__)

class SubAgentInitializeMiddleware(
    AgentMiddleware[ContextAgentState, ContextT, ResponseT]
):
    """Sub-agent initialization middleware"""
    
    @override
    def before_agent(self, state: ContextAgentState, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """Initialize the sub-agent: clear history messages and add the user query. When a deepagents subagent
           executes, it passes the tools_args returned by the LLM as a HumanMessage;
           here we need to clear the auto-generated description that is used as a HumanMessage.
        """
        sys_sub_conversation_id = state["sys_sub_conversation_id"]
        if not sys_sub_conversation_id:
            sys_sub_conversation_id =  state["sys_conversation_id"] + "_" + state["biz_id"]
        
        user_query = state["user_query"]
        
        return {
            "sys_parent_conversation_id": state["sys_conversation_id"],
            "sys_conversation_id": sys_sub_conversation_id,
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES),HumanMessage(content=user_query)]
        }