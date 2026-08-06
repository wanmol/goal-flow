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
    """初始化子agent中间件"""
    
    @override
    def before_agent(self, state: ContextAgentState, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """初始化子agent，清空历史消息，添加用户查询, deepagents subagent执行的时候会把大模型返回的tools_args作为humanmessage传递
           这里需要清空自动生成description作为humanmessage
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