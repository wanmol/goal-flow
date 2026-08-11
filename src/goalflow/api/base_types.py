from typing import Dict,Any
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Union, Literal
from enum import Enum

def format_stream_chunk(
    *,
    chunk_id: int,
    event_type: str,
    data: Dict[str, Any],
    workflow_run_id: str = None,
    answer: str = None,
    task_id: str = None,
    message_id: str = None,
    conversation_id: str = None,
    metadata: Dict[str, Any] = None,
    message: str = None,
) -> str:
    """Format a streaming chunk as SSE format."""
    chunk = ChatStreamChunk(
        chunk_id=str(chunk_id),
        event=event_type,
        # data=data,
        workflow_run_id=workflow_run_id,
        timestamp=datetime.utcnow().isoformat(),
    )
    if data is not None:
        chunk.data = data

    if task_id is not None:
        chunk.task_id = task_id
    if message_id is not None:
        chunk.message_id = message_id
    if conversation_id is not None:
        chunk.conversation_id = conversation_id

    if answer is not None:
        chunk.answer = answer

    if metadata is not None:
        chunk.metadata = metadata

    if message is not None:
        chunk.message = message

    # Format as Server-Sent Events
    return f"data: {chunk.model_dump_json()}\n\n"


# chat streaming chunk model
class ChatStreamChunk(BaseModel):
    """Streaming response chunk model."""

    chunk_id: str = Field(..., description="分块ID")
    event: str = Field(..., description="事件类型: 'message'|'update'|'error'|'done'")
    data: Dict[str, Any] = Field(None, description="分块数据")
    timestamp: str = Field(..., description="时间戳")
    answer: Optional[str] = Field(None, description="回答")
    task_id: str = Field(None, description="任务ID")
    message_id: str = Field(None, description="消息ID")
    conversation_id: str = Field(None, description="会话ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    message: Optional[str] = Field(None, description="错误消息，兼容dify")

# chat blocking response model
class ChatCompletionBlockingResponse(BaseModel):
    """Chat completion response model."""
    event: str = Field(default="message", description="事件类型: 非流式模式固定为message")
    task_id: str = Field(..., description="任务ID")
    id: str = Field(..., description="ID")
    message_id: str = Field(..., description="消息ID")
    conversation_id: str = Field(..., description="会话ID")

    mode: str = Field(default="chat", description="app模式: 固定为chat")

    answer: str = Field(None, description="回答")

    #created_at: str = Field(..., description="时间戳")
    
    metadata: Dict[str, Any] = Field(None, description="元数据")

    message: str = Field(None, description="错误消息，兼容dify")
    
    
    
#=========================Below is the interface format agreed upon for LLM application filing====================================
class ChatCompletionRequestMessagePart(BaseModel):
    """Input model for chat completion message part."""
    role: Literal["user", "model", "system"] = Field(..., description="角色")
    content: str = Field(..., description="内容")

# Request params are in openai format; the response format can be customized, defaulting to openai format too
class ChatCompletionRequest(BaseModel):
    """Input model for chat completion."""
    model: str = Field("", description="模型名称")
    dialogue: List[ChatCompletionRequestMessagePart] = Field(..., description="对话列表")
    stream: Optional[bool] = Field(default=True, description="是否流式响应")
    #temperature: Optional[float] = Field(default=0.7, description="温度参数")
    max_tokens: Optional[int] = Field(default=4000, description="最大token数")
    user: Optional[str] = Field(default="openai_canonical_general_user", description="用户ID")
    response_format: Optional[str] = Field(default="openai", description="响应格式")

# Added image generation request model
class ImageGenerationRequest(BaseModel):
    """Image generation request model."""
    dialogue: List[ChatCompletionRequestMessagePart] = Field(..., description="对话列表")
    size: Optional[str] = Field(default="1024*1024", description="图像尺寸")
    negative_prompt: Optional[str] = Field(default="", description="负面提示词")


# Added image generation response model
class ImageGenerationResponse(BaseModel):
    """Image generation response model."""
    status: str = Field(..., description="状态")
    reason: str = Field(..., description="原因")
    content: str = Field(..., description="生成的图像URL")


class ChatCompletionRequestMessageRole(Enum):
    """Chat completion request message role enum."""
    USER = "user"
    MODEL = "model"
#=========================Above is the interface format agreed upon for LLM application filing====================================
