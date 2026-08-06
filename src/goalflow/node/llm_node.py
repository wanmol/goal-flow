import json
import re
import uuid
from http.client import responses

from jinja2 import Template

from random import Random

from langchain_openai import AzureChatOpenAI, OpenAI
from langgraph.types import Command, Send
from pyexpat.errors import messages

from goalflow.llm import LLM
from goalflow.node.base import BaseNode, NodeOutput
from typing import Optional, Sequence, Dict, Tuple, Any, List
from goalflow.workflow_types import (
    LLMNodeModelConfig,
    MemoryConfig,
    ContextConfig,
    LLmNodePromptTemplate,
    PromptConfig, NodeVarConfig
)
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.utils import VariableResolver

from goalflow.config import get_logger

logger = get_logger(__name__)


class LLMNode(BaseNode):
    """
    Large Language Model node for AI text generation.
    This node processes prompts and generates responses using configured LLM models.
    """
    context: ContextConfig
    memory: MemoryConfig
    prompt_config: Optional[PromptConfig]
    prompt_template: Sequence[LLmNodePromptTemplate]
    model: LLMNodeModelConfig
    vision: Dict

    # read only
    __node_type = WfNodeType.LLM

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(self, *, context: ContextConfig, memory: MemoryConfig,
                 prompt_config: Optional[PromptConfig] = None,
                 prompt_template: Sequence[LLmNodePromptTemplate],
                 model: LLMNodeModelConfig, vision: Dict, **kwargs):
        super().__init__(**kwargs)
        self.context = context
        self.memory = memory
        self.prompt_template = prompt_template
        self.model = model
        self.vision = vision
        self.prompt_config = prompt_config
        self.streaming = True
        self.disable_streaming = False
        # 处理大模型参数
        self._format_completion_params()

    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute LLM processing with the given state.

        """

        try:
            # 调用大模型
            llm = LLM(
                context=self.context,
                prompt_config=self.prompt_config,
                prompt_template=self.prompt_template,
                memory=self.memory,
                model=self.model,
                vision=self.vision,
                streaming=self.streaming,
                disable_streaming=self.disable_streaming,
                state=state,
                node_id=self.formatted_name,
                llm_node=self
            )
            response = llm.invoke()
            content = response.content
            '''if (self.model.completion_params is not None
                    and "response_format" in self.model.completion_params
                    and self.model.completion_params["response_format"]["type"] == "json_object"):
                """
                千问大模型返回的是markdown格式，此处进行了格式化
                """
                content = self._format_json(content)'''
            if self.model.completion_params is not None and "response_format" in self.model.completion_params:
                if isinstance(self.model.completion_params["response_format"], dict) and self.model.completion_params["response_format"]["type"] == "json_object":
                    content = self._format_json(content)

            update_data = VariableResolver.format_output(node_id=self.id, outputs={"text": content})
           

            return Command(
                update=update_data,
                goto=self.next_node_ids

            )
            # return [Send(self.id,update_data)]
        except Exception as e:
            logger.error(f"llm invoke error: {e}", exc_info=True, node_id=self.formatted_name)

            return self._handle_error(e)

    def _handle_error(self, e):
        if not self.error_strategy:
            raise e

        strategy_handlers = {
            "default-value": lambda: Command(
                update=VariableResolver.format_output(
                    node_id=self.id,
                    outputs={"text": self.default_value[0]['value'] if self.default_value else ''}
                ),
                goto=self.next_node_ids
            ),
            "fail-branch": lambda: Command(
                update={"node_id": self.id, "source_handle": "fail-branch"},
                goto=self.fail_branch_node_ids
            )
        }

        handler = strategy_handlers.get(self.error_strategy)
        if not handler:
            raise ValueError(f"Invalid error strategy: {self.error_strategy}")

        return handler()

    def _format_completion_params(self):
        """
        转换dify 中的大模型参数，适配langchain的大模型调用参数
        """
        completion_params = self.model.completion_params
        if completion_params:
            for k, v in completion_params.items():
                if k == "response_format" and v == "json_object":
                    completion_params[k] = {
                        "type": "json_object"
                    }
                if k == "streaming":
                    self.streaming = v

    def _format_json(self, content: str) -> str:
        pattern = r'```json\s*([\s\S]*?)\s*```'
        match = re.search(pattern, content)
        if match:
            json_str = match.group(1)
        else:
            # 如果没有匹配到，尝试直接解析整个内容
            json_str = content
        return json_str

  