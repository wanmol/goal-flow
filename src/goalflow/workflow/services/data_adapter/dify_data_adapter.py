from typing import Generator

from goalflow.api.base_types import ChatCompletionBlockingResponse
from goalflow.workflow.services.data_adapter.abstract_data_adapter import AbstractDataAdapter


class DifyDataAdapter(AbstractDataAdapter):
    """Default (identity) adapter for the Dify wire protocol.

    goalflow's internal streaming/blocking format already *is* the Dify protocol,
    so this adapter passes data through unchanged. It exists so every supported
    protocol is represented by a concrete adapter and is uniformly discoverable
    alongside OpenAIDataAdapter and any custom adapters.
    """

    def __init__(self, config: dict = None):
        self.config = config

    def generate(self, generator: Generator[str, None, None]) -> Generator[str, None, None]:
        """流式消息转换：Dify 协议即内部格式，逐条透传。"""
        for chunk in generator:
            yield chunk

    def execute(self, data: ChatCompletionBlockingResponse) -> dict:
        """非流式消息转换：直接返回阻塞响应的 dict 形式。"""
        return data.model_dump()
