import json
from typing import Optional, Any, Dict, Callable

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.messages.ai import AIMessage
from langchain_openai import AzureChatOpenAI

from langgraph.graph.state import Command

from goalflow.workflow_types import MemoryConfig, LLMNodeModelConfig, ToolInput, AgentToolConfig
from goalflow.constants import WfNodeType
from goalflow.node import BaseNode
from goalflow.state import GenericState
from goalflow.tool.utils import VariableResolver
import time
import os

from goalflow.config import get_logger

logger = get_logger(__name__)


class AgentNode(BaseNode):
    agent_strategy_label: str | None = None
    agent_strategy_name: str | None = None
    agent_strategy_provider_name: str | None = None
    memory: MemoryConfig | None = None
    output_schema: Optional[Any] | None = None
    plugin_unique_identifier: str | None = None
    tools: AgentToolConfig
    tool_dict: dict[str, Callable[..., Any]] = {}
    # read only
    __node_type = WfNodeType.AGENT

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(
        self,
        *,
        instruction: ToolInput,
        query: ToolInput,
        model: LLMNodeModelConfig,
        output_schema: Optional[Any] | None = None,
        memory: MemoryConfig | None = None,
        agent_strategy_label: str | None = None,
        agent_strategy_name: str | None = None,
        tools: AgentToolConfig,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.instruction = instruction
        self.query = query
        self.model = model
        self.output_schema = output_schema
        self.memory = memory
        self.agent_strategy_label = agent_strategy_label
        self.agent_strategy_name = agent_strategy_name
        self.tools = tools

    def call(self, state: GenericState):
        variable_pool = self._merge_variables(state)

        node_instruction = VariableResolver.replace_template(
            template=self.instruction.value, variables=variable_pool
        )
        system_message = SystemMessage(node_instruction)
        user_message = HumanMessage(
            content=VariableResolver.replace_template(self.query.value, state)
        )

        messages = [system_message, user_message]
        tools, tool_choice = self._get_tools()
        llm = self._determine_llm()

        max_retries = 3
        tool_result = None
        for i in range(max_retries):
            try:
                start_time = time.perf_counter()
                response = llm.invoke(
                    input=messages, tools=tools, tool_choice=tool_choice
                )
                end_time = time.perf_counter()

                tool_result = self.handle_tool_calls(response, messages, llm)
                logger.info(
                    f"{self.formatted_name} invoke tool result: {tool_result} , cost time: {end_time - start_time} seconds."
                )
                break
            except Exception as e:
                if i < max_retries - 1:
                    # 去掉已经保存到了messages列表中的tool_call 消息
                    if len(messages) > 0 and hasattr(messages[-1], "tool_calls"):
                        messages = messages[:-1]
                    continue
                else:
                    raise e

        return Command(update=tool_result, goto=self.next_node_ids)

    def _get_tools(self):
        tools = []
        if self.tools and self.tools.value:
            for tool in self.tools.value:
                if tool.enabled and len(tool.schemas) > 0:
                    _properties = {}
                    _required = []
                    for schema in tool.schemas:
                        _properties[schema.name] = {
                            "type": schema.type,
                            "description": schema.label["zh_Hans"],
                        }
                        if schema.required:
                            _required.append(schema.name)

                    _function = {
                        "type": "function",
                        "function": {
                            "name": tool.tool_name,
                            "description": tool.tool_label,
                            "id": tool.tool_name,
                            "parameters": {
                                "type": "object",
                                "properties": _properties,
                                "required": _required,
                            },
                        },
                    }
                    tools.append(_function)

                    self.tool_dict[tool.tool_name] = tool.func
        return tools, "auto"

    # 处理模型响应并执行函数调用
    def handle_tool_calls(self, response, messages, llm):
        """处理模型返回的工具调用并执行相应函数"""
        additional_kwargs = response.additional_kwargs
        # 检查是否有工具调用
        if additional_kwargs and "tool_calls" in additional_kwargs:
            # 将模型的回复添加到消息历史中
            messages.append(response)
            logger.info(
                f"{self.formatted_name} handle_tool_calls start, messages: {messages}"
            )

            # 处理每个工具调用
            for tool_call in additional_kwargs["tool_calls"]:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                logger.info(
                    f"{self.formatted_name} handle_tool_calls execute tool, function:{function_name},args:{function_args}"
                )

                # 根据函数名调用相应的函数
                func = self.tool_dict.get(function_name)
                if self.tool_dict and callable(func):
                    function_response = func(**function_args)

                    # 将函数执行结果添加到消息历史中
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": function_name,
                            "content": function_response,
                        }
                    )

            # 再次调用模型，将函数结果送回模型生成最终回复
            second_response = llm.invoke(
                input=messages,
            )
            logger.info(
                f"{self.formatted_name} handle_tool_calls final answer: {second_response.content}"
            )
            output = VariableResolver.format_output(
                node_id=self.id,
                outputs={"text": second_response.content, "files": [], "json": []},
            )
            return output
        else:
            # 没有工具调用，直接返回响应
            return VariableResolver.format_output(
                node_id=self.id,
                outputs={"text": response.content, "files": [], "json": []},
            )

    def _merge_variables(self, state: GenericState) -> Dict[str, Any]:
        """
        使用高效的字典合并方式构建变量池
        """
        variable_pool = {
            "sys_query": state.get("sys_query"),
            "sys_dialogue_count": state.get("sys_dialogue_count"),
            "sys_conversation_id": state.get("sys_conversation_id"),
            "sys_user_id": state.get("sys_user_id"),
            "sys_files": state.get("sys_files"),
            "sys_app_id": state.get("sys_app_id"),
            "sys_workflow_id": state.get("sys_workflow_id"),
            "sys_workflow_run_id": state.get("sys_workflow_run_id"),
        }
        # 使用 dict.update() 比字典解包更高效
        variable_pool.update(state.get("input_variables", {}))
        variable_pool.update(state.get("output_variables", {}))
        variable_pool.update(state.get("conversation_variables", {}))
        return variable_pool

    def _determine_llm(self):
        if self.model.provider == "langgenius/azure_openai/azure_openai":
            return AzureChatOpenAI(
                api_key=os.environ['OPENAI_KEY'],
                azure_endpoint=os.environ['OPENAI_ENDPOINT'],
                api_version="2025-03-01-preview",
                model=self.model.name,
                **self.model.completion_params,
            )
        else:
            return ChatTongyi(
                api_key=os.environ['DASHSCOPE_KEY'],
                base_url=os.environ['DASHSCOPE_ENDPOINT'],
                model=self.model.name,
                **self.model.completion_params,
            )
