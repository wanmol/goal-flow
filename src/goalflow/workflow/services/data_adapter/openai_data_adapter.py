from goalflow.api.base_types import ChatStreamChunk,ChatCompletionBlockingResponse
from goalflow.workflow.services.data_adapter.abstract_data_adapter import AbstractDataAdapter
from typing import Generator, Dict, Any


class OpenAIDataAdapter(AbstractDataAdapter):
    """OpenAI data adapter."""
    def __init__(self, config: dict = None):
        self.config = config
        
    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """Generate stream of messages from generator."""
        for chunk in generator:
            chunk = chunk.strip()
            if not chunk.startswith("data: "):
                continue
            
            event_data = chunk[6:]
            
            #event_data = event_data.replace("\n","")
            
            chunk = ChatStreamChunk.model_validate_json(event_data)
            
            # 只处理message或error事件
            if chunk.event in ["message", "error"]:
                openai_format = self._convert_chunk_to_openai_format(chunk)
                yield f"data:  {openai_format}\n\n"
            else:
                continue
            
    def _convert_chunk_to_openai_format(self, chunk: ChatStreamChunk) -> Dict[str, Any]:
        """
        将ChatStreamChunk转换为OpenAI格式
        """
        # 只处理event=message或event=error的情况
        if chunk.event == "message":
            # 判断是否是最后一条消息，这里我们假设如果answer为空或chunk有某种结束标志，则认为是最后一条
            # 由于我们无法确定具体什么条件下是最后一条消息，我们添加一个逻辑来检测是否是结束
            # 这里可以根据具体业务逻辑进行调整，比如检查chunk中的某些字段来判断是否是结束
            finish_reason = None
            delta_content = chunk.answer if hasattr(chunk, 'answer') and chunk.answer else ""
            
            # 如果消息内容为空且可能代表结束状态，设置finish_reason为stop
            # 这里需要根据实际情况调整判断条件，例如通过meta信息或其他字段判断
            is_last_message = False
            if hasattr(chunk, 'meta') and isinstance(chunk.meta, dict):
                # 检查元数据中是否有结束标志
                is_last_message = chunk.meta.get('is_last', False) or \
                                 chunk.meta.get('finish', False) or \
                                 chunk.meta.get('end_of_stream', False)
            
            # 或者如果answer为空字符串，可能是结束信号
            if not delta_content :
                # 如果有返回码且为正常结束码，可能表示结束
                is_last_message = True
            
            # 根据是否是最后一条消息设置finish_reason
            finish_reason = "stop" if is_last_message else ""
            
            return {
                "content" : "",
                "choices": [
                    {
                        "delta": chunk.answer,"finish_reason": finish_reason
                    }
                ],
                "finish_reason": finish_reason,
                "status": "success",
                "reason": "success"
            }
        elif chunk.event == "error":
            return {
                "content": "",
                "choices": [],
                "finish_reason": "stop",
                "status": "failed",
                "reason": chunk.message
            }
        else:
            # 对于其他事件类型，返回空的delta
            return {
                "id": f"chatcmpl-{chunk.message_id}",
                "object": "chat.completion.chunk",
                "created": self._get_current_timestamp(),
                "model": "gpt-3.5-turbo",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": None
                    }
                ]
            }

        
    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """Execute data."""
        ret = {
            "content": data.answer,
            "choices": [],
            "finish_reason": "stop",
            "status": "success",
            "reason": "success"
        }
        
        return ret
