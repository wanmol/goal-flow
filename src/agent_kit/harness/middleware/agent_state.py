from langchain.agents.middleware.types import AgentState, ResponseT
from langgraph.typing import ContextT
from typing import Optional

class ContextAgentState(AgentState):
    sys_conversation_id: Optional[str]
    sys_parent_conversation_id: Optional[str]
    
    # 子agent会话id【可选】  如果没有传递，默认为sys_conversation_id + "_" + biz_id
    sys_sub_conversation_id: Optional[str]
    
    sys_user_id: str
    sys_app_id: str
    user_query: str
    biz_id: str
