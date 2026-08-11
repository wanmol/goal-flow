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
    Node run started event
    """
    pass


class NodeRunSucceededEvent(BaseNodeEvent):
    """
    Node run succeeded event
    """
    outputs: Optional[dict[str, Any]] = None
    """outputs"""
    
class NodeRunStoppedEvent(BaseNodeEvent):
    """
    Workflow stopped event
    """
    outputs: Optional[dict[str, Any]] = None

  
class NodeRunInterruptEvent(BaseGraphEvent):
    """
    Flow interrupt event
    """
    outputs: Optional[dict[str, Any]] = None
 
class NodeRunControlEvent(BaseGraphEvent):
    """
    Node control event
    For example, for research report creation, if the first streaming output content does not meet expectations and a second generation is performed, a control event needs to be sent
    to tell the frontend to clear the current content and prepare to receive new streaming output
    """
    outputs: Optional[dict[str, Any]] = None
    
 
class NodeRunFailedEvent(BaseNodeEvent):
    """
    Node run failed event
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

# text fragment actively pushed by a node via get_stream_writer (e.g. AgentBaseNode.stream_text).
# the event data looks like {"node_id": str, "text": str}, converted by the chunk processor into a NodeRunStreamChunkEvent.
CUSTOM_STREAM_MODE_DIRECT_OUTPUT = sys.intern("__DIRECT_OUTPUT__")

WF_NODE_CONTROL_EVENT_NAME = sys.intern("__node_control__")

