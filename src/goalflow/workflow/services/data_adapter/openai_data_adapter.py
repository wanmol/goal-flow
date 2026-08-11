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
            
            # only handle message or error events
            if chunk.event in ["message", "error"]:
                openai_format = self._convert_chunk_to_openai_format(chunk)
                yield f"data:  {openai_format}\n\n"
            else:
                continue
            
    def _convert_chunk_to_openai_format(self, chunk: ChatStreamChunk) -> Dict[str, Any]:
        """
        Convert ChatStreamChunk to OpenAI format
        """
        # only handle the case of event=message or event=error
        if chunk.event == "message":
            # determine whether it is the last message; here we assume that if answer is empty or the chunk has some end marker, it is the last one
            # since we cannot determine the specific condition for the last message, we add a logic to detect whether it is the end
            # this can be adjusted according to specific business logic, e.g. checking certain fields in the chunk to determine whether it is the end
            finish_reason = None
            delta_content = chunk.answer if hasattr(chunk, 'answer') and chunk.answer else ""

            # if the message content is empty and may represent an end state, set finish_reason to stop
            # the judgment condition here needs to be adjusted according to the actual situation, e.g. judging via meta information or other fields
            is_last_message = False
            if hasattr(chunk, 'meta') and isinstance(chunk.meta, dict):
                # check whether there is an end marker in the metadata
                is_last_message = chunk.meta.get('is_last', False) or \
                                 chunk.meta.get('finish', False) or \
                                 chunk.meta.get('end_of_stream', False)

            # or if answer is an empty string, it may be an end signal
            if not delta_content :
                # if there is a return code and it is a normal end code, it may indicate the end
                is_last_message = True

            # set finish_reason based on whether it is the last message
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
            # for other event types, return an empty delta
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
