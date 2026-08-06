from typing import TypedDict,Optional,Any
from pydantic import BaseModel,Field
from goalflow.constants import *

import sys

class StreamEventChunk(BaseModel) :
    pass 

class BaseGraphEvent(BaseModel):
    pass 

class GraphRunStartedEvent(BaseGraphEvent):
    pass

class GraphRunSucceededEvent(BaseGraphEvent):
    outputs: Optional[dict[str, Any]] = None
    """outputs"""
    
class GraphRunFailedEvent(BaseGraphEvent):
    error: str = Field(..., description="failed reason")
    exceptions_count: int = Field(description="exception count", default=0)
    
class BaseNodeEvent(BaseGraphEvent):
    node_id: str 
    node_type: str 
    node_data: dict 


class NodeRunStartedEvent(BaseNodeEvent):
    """
    节点运行开始事件
    """
    pass


class NodeRunSucceededEvent(BaseNodeEvent):
    """
    节点运行成功事件
    """
    outputs: Optional[dict[str, Any]] = None
    """outputs"""
    
class NodeRunStoppedEvent(BaseNodeEvent):
    """
    工作流停止事件
    """
    outputs: Optional[dict[str, Any]] = None

  
class NodeRunInterruptEvent(BaseGraphEvent):
    """
    流程中断事件    
    """
    outputs: Optional[dict[str, Any]] = None
 
class NodeRunControlEvent(BaseGraphEvent):
    """
    节点控制事件  
    比如对于研报创作，如果第一次流式输出内容不符合预期，进行第二次生成，需要发送一个控制事件，
    告诉前端清空当前内容，准备接收新的流式输出    
    """
    outputs: Optional[dict[str, Any]] = None
    
 
class NodeRunFailedEvent(BaseNodeEvent):
    """
    节点运行失败事件
    """
    error: str = Field(..., description="error")
    
class NodeRunStreamChunkEvent(BaseNodeEvent):
    chunk_content: str = Field(..., description="chunk content")
    #from_variable_selector: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = Field(None, description="metadata")
    
class ProxyStreamDataChunk(BaseModel) :
    data : str = Field(..., description="stream data chunk")

# "values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"
LANGGRAPH_STREAM_MODE_UPDATES = sys.intern("updates")
LANGGRAPH_STREAM_MODE_MESSAGES = sys.intern("messages")
LANGGRAPH_STREAM_MODE_VALUES = sys.intern("values")
LANGGRAPH_STREAM_MODE_CHECKPOINTS = sys.intern("checkpoints")
LANGGRAPH_STREAM_MODE_TASKS = sys.intern("tasks")
LANGGRAPH_STREAM_MODE_DEBUG = sys.intern("debug")
LANGGRAPH_STREAM_MODE_CUSTOM = sys.intern("custom")

CUSTOM_STREAM_MODE_PASSTHROUGH = sys.intern("__PASSTHROUGH__")

# 节点通过 get_stream_writer 主动推送的文本片段（如 AgentBaseNode.stream_text）。
# 事件数据形如 {"node_id": str, "text": str}，由 chunk processor 转成 NodeRunStreamChunkEvent。
CUSTOM_STREAM_MODE_DIRECT_OUTPUT = sys.intern("__DIRECT_OUTPUT__")

WF_NODE_CONTROL_EVENT_NAME = sys.intern("__node_control__")

