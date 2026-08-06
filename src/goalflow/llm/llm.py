import json
from typing import Optional, Sequence, Dict, Any, Tuple, TYPE_CHECKING,List

from jinja2 import Template
from langchain_community.chat_models import ChatTongyi
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import AIMessage

from goalflow.cache import RedisClusterManager

from goalflow.utils import ChatCompletionRequestCache

from goalflow.api.base_types import ChatCompletionRequest, ChatCompletionRequestMessagePart

import os

from goalflow.workflow_types import (
    LLMNodeModelConfig,
    MemoryConfig,
    ContextConfig,
    LLmNodePromptTemplate,
    PromptConfig,
    VisionConfig
)

from goalflow.constants import (
    CHAT_COMPLETION_REQUEST_REDIS_KEY_FMT
)

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    from goalflow.node.base import NodeOutput

from goalflow.service.message_service import MessageService
from goalflow.state import GenericState

# from storage.mysql.message_storage import MessageStorage

from goalflow.tool.utils import VariableResolver

import uuid

from goalflow.config import get_logger,trace_info as trace_info_ctx, var_child_runnable_config

logger = get_logger(__name__)


#非OpenAI标准参数列表
EXTRA_BODY_KEYS = [
    #控制DeepSeek-V4系列模型的推理力度
    "reasoning_effort",
    
    #思考过程的最大 Token 数。适用于Qwen3.7、Qwen3.6、Qwen3.5、Qwen3-VL、Qwen3 的商业版与开源版模型
    "thinking_budget",
    
    #是否将对话历史中 assistant 消息的 reasoning_content 拼接至模型输入。适用于需要模型参考历史思考过程的场景
    #目前支持qwen3.7-max、qwen3.7-max-2026-05-20以及后续快照、qwen3.6-max-preview、qwen3.7-plus、qwen3.7-plus-2026-05-26、qwen3.6-plus、qwen3.6-plus-2026-04-02、kimi-k2.6（阿里云百炼部署）、kimi-k2.7-code（阿里云百炼部署，默认开启）、kimi/kimi-k2.7-code-highspeed（月之暗面直供，默认开启）、kimi/kimi-k2.7-code（月之暗面直供，默认开启）
    "preserve_thinking",
    
    #控制稀宇科技直供的MiniMax/MiniMax-M3 的思考模式。
    "thinking_mode",
    
    #使用混合思考（回复前既可思考也可不思考）模型时，是否开启思考模式。适用于 Qwen3.7、Qwen3.6、Qwen3.5、Qwen3、Qwen3-Omni-Flash、Qwen3-VL模型，以及 DeepSeek-V4-Pro/V4-Flash 系列（阿里云直供）、DeepSeek-V3.2/V3.2-exp/V3.1 系列（阿里云直供、硅基流动直供、快手万擎直供）、Kimi-K2.7-code（仅思考模型）、Kimi-K2.6/K2.5 系列（阿里云直供、月之暗面直供）、GLM 系列。DeepSeek-V4 系列默认开启思考，可通过 reasoning_effort 参数调整推理力度
    "enable_thinking"
]

class LLM:

    context: ContextConfig
    memory: MemoryConfig
    prompt_config: Optional[PromptConfig]
    prompt_template: Sequence[LLmNodePromptTemplate]
    model: LLMNodeModelConfig
    vision: VisionConfig
    state: GenericState
    streaming: bool
    # 控制流式输出， streaming在langgraph环境无效， disable_streaming有效
    disable_streaming: bool

    def __init__(
        self,
        *,
        context: ContextConfig,
        memory: MemoryConfig,
        prompt_config: Optional[PromptConfig] = None,
        prompt_template: Sequence[LLmNodePromptTemplate],
        model: LLMNodeModelConfig,
        vision: VisionConfig,
        disable_streaming: bool = False, 
        streaming: bool = False,
        state: GenericState,
        node_id: str = "",
        llm_node: "LLMNode" = None,
    ):

        self.context = context
        self.memory = memory
        self.prompt_config = prompt_config or {}
        self.prompt_template = prompt_template or []
        self.model = dict(model) if isinstance(model, dict) else model
        self.vision = vision or {}
        self.state = state or {}
        self.streaming = streaming
        self.disable_streaming = disable_streaming
        self.node_id = node_id
        self.llm_node = llm_node

    def invoke(self) -> "NodeOutput":
        variable_pool = self._merge_variables(self.state)
        # 创建 prompt_template 的副本，避免修改原始数据
        _prompt_template = [
            LLmNodePromptTemplate(
                id=template.id,
                role=template.role,
                text=template.text,
                jinja2_text=template.jinja2_text,
                edition_type=template.edition_type,
            )
            for template in self.prompt_template
        ]

        # 1. 处理 prompt 模板（合并 jinja2_text -> text，判断是否存在 jinja2）
        prompt_template, exists_jinja2 = self._prepare_jinja2_template(_prompt_template)

        # 2. 若存在 jinja2：替换 jinja2 变量（使用缓存模板）
        if exists_jinja2:
            prompt_template = self._replace_jinja2_variables(
                prompt_template, variable_pool
            )

        # 3. 替换 basic 变量（VariableResolver）
        prompt_template = self._replace_basic_variables(prompt_template, self.state)

        chat_completion_request:ChatCompletionRequest = None
        
        # 4. History 消息处理
        if self.memory and self.memory.window:
            # 会话流中，启用历史消息
            if self.memory.window.get("enabled", False):
                
                sys_openai_param :bool = self.state.get("sys_openai_param", False)
                
                message_size = self.memory.window.get("size", 20)
                
                if not sys_openai_param:
                    conversation_id = self.state.get("sys_conversation_id")
                    
                    if conversation_id is not None:
                        history = MessageService.get_llm_template_by_conversation_id(
                            conversation_id
                        )
                        prompt_template = self._merge_sys_template_and_history(
                            prompt_template=prompt_template,
                            history=history,
                            prompt_length=message_size,
                        )   
                # 对于历史对话记录是通过参数传递的， 需要把参数中的message拼接到prompt_template中， 而不是查数据库获取历史记录
                else:
                    chat_completion_request:ChatCompletionRequest = ChatCompletionRequestCache.get_chat_completion_request(state=self.state)
                    if chat_completion_request:
                        his_messages:List[ChatCompletionRequestMessagePart] = chat_completion_request.dialogue
                        his_messages:List[ChatCompletionRequestMessagePart] = his_messages[-message_size:-1]
                        
                        for h in his_messages:
                            prompt_template.append(
                                LLmNodePromptTemplate(role=h.role, text=h.content)
                            )
                            
                    # 重置过期时间  （历史消息可能会在后续llm节点继续使用）
                    ChatCompletionRequestCache.perpetuate_request_cache(state=self.state)
            else:
                # 会话流，不启用历史消息，只保留第一条记录   prompt_template至少有一条role=system的数据
                # comments by wangwei 20260414 这里如果设计添加了多个template（比如问答示例）是否要保留？TODO
                prompt_template = [prompt_template[0]]
        # else:
        #     # 工作流中，默认查询20条历史消息
        #     conversation_id = self.state.get("sys_conversation_id")
        #     if conversation_id is not None:
        #         history = MessageService.get_llm_template_by_conversation_id(
        #             conversation_id
        #         )

        #         prompt_template = self._merge_sys_template_and_history(
        #             prompt_template=prompt_template,
        #             history=history,
        #             prompt_length=20,
        #         )
        user_input = None
        if self.memory and self.memory.query_prompt_template:
            user_input = self.memory.query_prompt_template

        if user_input:
            prompt_template.append(
                LLmNodePromptTemplate(
                    role="user",
                    text=VariableResolver.replace_template(user_input, self.state),
                )
            )
        
        # 多模态参数处理
        if self.vision and self.vision.enabled:
            # 多模态暂时只支持 openai模型！！！
            #if self.model.provider != "langgenius/azure_openai/azure_openai":
            #    raise ValueError("vision is only supported by langgenius/azure_openai/azure_openai")
                
            vision_configs = self.vision.configs
            var_images = vision_configs.variable_selector
            if not var_images:
                raise ValueError("vision configs must have variable_selector")
                
            image_obj = VariableResolver.resolve_value_selector(var_images, self.state)[0]
            # 暂只支持远端存储的图片
            image_url = image_obj.get("remote_url")
            if not image_url:
                raise ValueError("file param must have remote_url")
            
            template:LLmNodePromptTemplate = prompt_template[-1]
            text = template.text
            multimodal_content=[
                {"type":"image_url","image_url":{"url":image_url}},
                {"type":"text","text":text}
            ]
            template.multimodal_content = multimodal_content
            template.text = ""
            
                
            # prompt_template.append(
            #     LLmNodePromptTemplate(
            #         role="user",
            #         text="",
            #         multimodal_content=[
            #             {"type":"image_url","image_url":{"url":image_url}},
            #             {"type":"text","text":VariableResolver.replace_template(user_input, self.state)}
            #         ],
            #     )
            # )

        # 5. 构建 messages（使用本地变量减少属性查找）
        messages = [{"role": p.role, "content": p.multimodal_content if p.multimodal_content else p.text} for p in prompt_template]

        logger.info("llm request", prompts=messages,mode=self.model.name,node_id=self.node_id)
        
        # 6. 调用 LLM
        llm = self._determine_llm(self.vision and self.vision.enabled, chat_completion_request)
        
        #span:Span = self.llm_node.start_trace() if self.llm_node is not None else None

        result = llm.invoke(messages)
        
        # 调用 LLMNode 的 set_input_output 方法，设置 trace 的 input 和 output
        if self.llm_node is not None:
            self.llm_node.set_input_output(messages, result)
        
        #if span:
        #    self.llm_node.end_trace(span, messages, result.content)

        logger.info("llm response", result=result,node_id=self.node_id)

        #处理 json_schema 类型的返回reslut
        response_format = self.model.completion_params.get("response_format")
        if response_format == "json_schema":
            raw = result.get("raw", AIMessage)
            if isinstance(raw, AIMessage):
                result = raw
            else:
                logger.error("raw 不是 AIMessage 类型: ", raw=raw)

        return result

    def _merge_sys_template_and_history(
        self,
        *,
        prompt_template: Sequence[LLmNodePromptTemplate],
        history: Sequence[Dict[str, Any]],
        prompt_length: int = 20,
    ) -> Sequence[LLmNodePromptTemplate]:
        # 1. 创建副本，避免修改原始数据
        merged_result = list(prompt_template)
        if not history:
            return merged_result
        # 2. 计算可添加的历史记录长度
        available_slots = prompt_length - len(prompt_template)
        if available_slots <= 0:
            return merged_result
        # 3. 确保历史记录长度为偶数（user-assistant对话对）
        max_history_count = (available_slots // 2) * 2
        if max_history_count <= 0:
            return merged_result

        # 4. 验证并转换历史记录（逆序取最近的记录）
        try:
            # 取最近的记录，限制数量
            history = history[::-1]
            recent_history = (
                history[-max_history_count:]
                if len(history) > max_history_count
                else history
            )

            history_templates = []
            for h in recent_history:
                # 安全检查
                if not isinstance(h, dict) or "role" not in h or "text" not in h:
                    logger.error(f"History record format error: {h}")
                    raise ValueError(f"历史记录格式错误: {h}")

                history_templates.append(
                    LLmNodePromptTemplate(role=h["role"], text=h["text"])
                )

            # 5. 添加到结果中
            merged_result.extend(history_templates)

        except (KeyError, TypeError, ValueError) as e:
            # 记录错误但不中断流程
            logger.warning(f"Merge history record error: {e}")
            # 可以选择返回原始模板或抛出异常
            return merged_result

        return merged_result

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
        variable_pool.update(state.get("input_variables", {}))
        variable_pool.update(state.get("output_variables", {}))
        variable_pool.update(state.get("conversation_variables", {}))
        return variable_pool

    def _replace_basic_variables(
        self, prompt_template: Sequence[LLmNodePromptTemplate], state: Dict[str, Any]
    ) -> Sequence[LLmNodePromptTemplate]:
        """
        利用 VariableResolver 替换 {{...}} 类模板
        - 使用本地引用减少全局查找开销
        """
        replace = VariableResolver.replace_template

        for prompt in prompt_template:
            prompt.text = replace(prompt.text, state)
        return prompt_template

    def _replace_jinja2_variables(
        self,
        prompt_template: Sequence[LLmNodePromptTemplate],
        variable_pool: Dict[str, Any],
    ) -> Sequence[LLmNodePromptTemplate]:
        """
        使用 Jinja2 渲染，缓存已编译模板以提升性能
        prompt_config.jinja2_variables: list of selectors -> 先解析为 variables dict
        """
        variables: Dict[str, Any] = {}
        pcfg = self.prompt_config or {}
        for sel in pcfg.jinja2_variables or []:
            var_name = sel.variable
            value_selector = sel.value_selector
            variables[var_name] = VariableResolver.resolve_value_selector(
                value_selector, self.state
            )

        for template in prompt_template:
            if template.edition_type == "jinja2":
                tpl = Template(template.text)
                template.text = tpl.render(variables)
        return prompt_template

    def _prepare_jinja2_template(
        self, prompt_template: Sequence[LLmNodePromptTemplate]
    ) -> Tuple[Sequence[LLmNodePromptTemplate], bool]:
        """
        合并 jinja2_text -> text 并返回是否存在 jinja2 模式
        - 不在原 list 原地修改，返回新的列表避免外部副作用
        """
        exists_jinja2 = False

        for prompt in prompt_template:
            jinja2_text = prompt.jinja2_text
            if prompt.edition_type == "jinja2" and jinja2_text:
                exists_jinja2 = True
                prompt.text = jinja2_text
        return prompt_template, exists_jinja2

    def _determine_llm(self,is_vision: bool = False, chat_completion_request: ChatCompletionRequest = None):
        # 提取显式参数
        completion_params = self.model.completion_params.copy() if self.model.completion_params else {}
        temperature = completion_params.pop("temperature", 0.7)
        max_tokens = completion_params.pop("max_tokens", 4000)
        
        if chat_completion_request:
            max_tokens = chat_completion_request.max_tokens
        
        extra_body = completion_params.pop("extra_body", None)
        from langchain_openai import ChatOpenAI
        if self.model.provider == "langgenius/azure_openai/azure_openai":
            model = AzureChatOpenAI(
                api_key=os.environ['OPENAI_KEY'],
                azure_endpoint=os.environ['OPENAI_ENDPOINT'],
                api_version="2025-03-01-preview",
                model=self.model.name,
                temperature=temperature,  # 显式传递
                max_tokens=max_tokens,    # 显式传递
                model_kwargs=completion_params,  # 其他参数
                streaming=self.streaming,
            )
            # Azure OpenAI: 处理 response_format（兼容字符串和字典）
            response_format = self.model.completion_params.get("response_format")
            if response_format:
                if isinstance(response_format, str) and response_format == "json_object":
                    return model.bind(response_format={"type": "json_object"})
                elif isinstance(response_format, str) and response_format == "json_schema":
                    model.model_kwargs={}
                    json_schema = self.model.completion_params.get("json_schema")
                    json_schema_dict_real={}
                    if isinstance(json_schema, str):
                        try:
                            json_schema_dict = json.loads(json_schema)
                            if isinstance(json_schema_dict, dict):
                                json_schema_dict_real=json_schema_dict
                            else:
                                logger.error(f"警告：字符串解析结果不是字典，类型为 {type(json_schema)}")
                        except json.JSONDecodeError as e:
                            logger.error(f"json_schema_dict 失败: {e}")

                    bound_model = model.with_structured_output(
                            schema=json_schema_dict_real,
                            method="json_schema",
                            include_raw=True
                    )
                    return bound_model
                elif isinstance(response_format, dict):
                    return model.bind(response_format=response_format)
            return model
        else:
            if is_vision or any(v in self.model.name for v in ("qwen3.5", "qwen3.6", "qwen3.7")):
                for key in EXTRA_BODY_KEYS:
                    if key in completion_params:
                        extra_body = extra_body or {}
                        extra_body[key] = completion_params.pop(key)
                # 如果是视觉模型，使用ChatOpenAI接口SDK，ChatTongyi接口不支持
                return ChatOpenAI(
                    base_url=os.environ['DASHSCOPE_ENDPOINT'],
                    api_key=os.environ['DASHSCOPE_KEY'],  # Can be any string
                    model=self.model.name,
                    temperature=temperature,  # 显式传递
                    max_tokens=max_tokens,    # 显式传递
                    model_kwargs=completion_params,  # 包含 response_format 的其他参数
                    streaming=self.streaming,
                    extra_body=extra_body
                    )
            # 通义千问: response_format 直接通过 model_kwargs 传递（已经是字典格式）
            return ChatTongyi(
                api_key=os.environ['DASHSCOPE_KEY'], 
                base_url=os.environ['DASHSCOPE_ENDPOINT'],
                model=self.model.name,
                temperature=temperature,  # 显式传递
                max_tokens=max_tokens,    # 显式传递
                model_kwargs=completion_params,  # 包含 response_format 的其他参数
                streaming=self.streaming,
            )
    
    def get_model(self):
        """
        获取 LangChain 兼容的 LLM 模型实例
        
        用于 Agent 等需要直接访问 LLM 模型的场景
        
        Returns:
            LangChain LLM 模型实例（ChatTongyi 或 AzureChatOpenAI）
        """
        return self._determine_llm()