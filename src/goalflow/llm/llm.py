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

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from goalflow.node.base import NodeOutput

from goalflow.service.message_service import MessageService
from goalflow.state import GenericState

# from storage.mysql.message_storage import MessageStorage

from goalflow.tool.utils import VariableResolver

import uuid

from goalflow.config import get_logger,trace_info as trace_info_ctx, var_child_runnable_config

logger = get_logger(__name__)


#Non-OpenAI-standard parameter list
EXTRA_BODY_KEYS = [
    #Controls the reasoning effort of the DeepSeek-V4 series models
    "reasoning_effort",

    #Maximum number of tokens for the thinking process. Applies to the commercial and open-source versions of Qwen3.7, Qwen3.6, Qwen3.5, Qwen3-VL, Qwen3
    "thinking_budget",

    #Whether to append the reasoning_content of assistant messages in the conversation history to the model input. For scenarios where the model needs to reference the historical thinking process
    #Currently supports qwen3.7-max, qwen3.7-max-2026-05-20 and later snapshots, qwen3.6-max-preview, qwen3.7-plus, qwen3.7-plus-2026-05-26, qwen3.6-plus, qwen3.6-plus-2026-04-02, kimi-k2.6 (deployed on Alibaba Cloud Bailian), kimi-k2.7-code (deployed on Alibaba Cloud Bailian, enabled by default), kimi/kimi-k2.7-code-highspeed (supplied directly by Moonshot, enabled by default), kimi/kimi-k2.7-code (supplied directly by Moonshot, enabled by default)
    "preserve_thinking",

    #Controls the thinking mode of MiniMax/MiniMax-M3 supplied directly by MiniMax.
    "thinking_mode",

    #Whether to enable thinking mode when using a hybrid-thinking model (which may or may not think before replying). Applies to Qwen3.7, Qwen3.6, Qwen3.5, Qwen3, Qwen3-Omni-Flash, Qwen3-VL models, as well as the DeepSeek-V4-Pro/V4-Flash series (supplied directly by Alibaba Cloud), DeepSeek-V3.2/V3.2-exp/V3.1 series (supplied directly by Alibaba Cloud, SiliconFlow, Kuaishou Wanqing), Kimi-K2.7-code (thinking model only), Kimi-K2.6/K2.5 series (supplied directly by Alibaba Cloud, Moonshot), GLM series. The DeepSeek-V4 series enables thinking by default and can adjust reasoning effort via the reasoning_effort parameter
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
    # Controls streaming output; streaming has no effect in the langgraph environment, disable_streaming does
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
        # Create a copy of prompt_template to avoid modifying the original data
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

        # 1. Process the prompt template (merge jinja2_text -> text, determine whether jinja2 is present)
        prompt_template, exists_jinja2 = self._prepare_jinja2_template(_prompt_template)

        # 2. If jinja2 is present: replace jinja2 variables (using the cached template)
        if exists_jinja2:
            prompt_template = self._replace_jinja2_variables(
                prompt_template, variable_pool
            )

        # 3. Replace basic variables (VariableResolver)
        prompt_template = self._replace_basic_variables(prompt_template, self.state)

        chat_completion_request:ChatCompletionRequest = None

        # 4. History message processing
        if self.memory and self.memory.window:
            # In a conversation flow, enable history messages
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
                # For history where conversation records are passed via parameters, the messages in the parameters need to be appended to prompt_template, rather than querying the database for history
                else:
                    chat_completion_request:ChatCompletionRequest = ChatCompletionRequestCache.get_chat_completion_request(state=self.state)
                    if chat_completion_request:
                        his_messages:List[ChatCompletionRequestMessagePart] = chat_completion_request.dialogue
                        his_messages:List[ChatCompletionRequestMessagePart] = his_messages[-message_size:-1]

                        for h in his_messages:
                            prompt_template.append(
                                LLmNodePromptTemplate(role=h.role, text=h.content)
                            )

                    # Reset the expiration time (history messages may continue to be used in subsequent llm nodes)
                    ChatCompletionRequestCache.perpetuate_request_cache(state=self.state)
            else:
                # Conversation flow, history messages not enabled, keep only the first record; prompt_template has at least one record with role=system
                # comments by wangwei 20260414 If multiple templates are added here (e.g. Q&A examples), should they be kept? TODO
                prompt_template = [prompt_template[0]]
        # else:
        #     # In the workflow, query 20 history messages by default
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
        
        # Multimodal parameter processing
        if self.vision and self.vision.enabled:
            # Multimodal currently only supports openai models!!!
            #if self.model.provider != "langgenius/azure_openai/azure_openai":
            #    raise ValueError("vision is only supported by langgenius/azure_openai/azure_openai")

            vision_configs = self.vision.configs
            var_images = vision_configs.variable_selector
            if not var_images:
                raise ValueError("vision configs must have variable_selector")

            image_obj = VariableResolver.resolve_value_selector(var_images, self.state)[0]
            # Currently only supports remotely stored images
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

        # 5. Build messages (use local variables to reduce attribute lookups)
        messages = [{"role": p.role, "content": p.multimodal_content if p.multimodal_content else p.text} for p in prompt_template]

        logger.info("llm request", prompts=messages,mode=self.model.name,node_id=self.node_id)

        # 6. Call the LLM
        llm = self._determine_llm(self.vision and self.vision.enabled, chat_completion_request)
        
        #span:Span = self.llm_node.start_trace() if self.llm_node is not None else None

        result = llm.invoke(messages)

        logger.info("llm response", result=result,node_id=self.node_id)

        #Handle result of type json_schema
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
        # 1. Create a copy to avoid modifying the original data
        merged_result = list(prompt_template)
        if not history:
            return merged_result
        # 2. Compute the length of history records that can be added
        available_slots = prompt_length - len(prompt_template)
        if available_slots <= 0:
            return merged_result
        # 3. Ensure the history record length is even (user-assistant conversation pairs)
        max_history_count = (available_slots // 2) * 2
        if max_history_count <= 0:
            return merged_result

        # 4. Validate and convert history records (take the most recent records in reverse order)
        try:
            # Take the most recent records, limiting the count
            history = history[::-1]
            recent_history = (
                history[-max_history_count:]
                if len(history) > max_history_count
                else history
            )

            history_templates = []
            for h in recent_history:
                # Safety check
                if not isinstance(h, dict) or "role" not in h or "text" not in h:
                    logger.error(f"History record format error: {h}")
                    raise ValueError(f"历史记录格式错误: {h}")

                history_templates.append(
                    LLmNodePromptTemplate(role=h["role"], text=h["text"])
                )

            # 5. Add to the result
            merged_result.extend(history_templates)

        except (KeyError, TypeError, ValueError) as e:
            # Log the error but do not interrupt the flow
            logger.warning(f"Merge history record error: {e}")
            # Can choose to return the original template or raise an exception
            return merged_result

        return merged_result

    def _merge_variables(self, state: GenericState) -> Dict[str, Any]:
        """
        Build the variable pool using an efficient dictionary merge
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
        Use VariableResolver to replace {{...}}-style templates
        - Use local references to reduce global lookup overhead
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
        Render using Jinja2, caching compiled templates to improve performance
        prompt_config.jinja2_variables: list of selectors -> first resolved into a variables dict
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
        Merge jinja2_text -> text and return whether jinja2 mode exists
        - Does not modify the original list in place; returns a new list to avoid external side effects
        """
        exists_jinja2 = False

        for prompt in prompt_template:
            jinja2_text = prompt.jinja2_text
            if prompt.edition_type == "jinja2" and jinja2_text:
                exists_jinja2 = True
                prompt.text = jinja2_text
        return prompt_template, exists_jinja2

    def _determine_llm(self,is_vision: bool = False, chat_completion_request: ChatCompletionRequest = None):
        # Extract explicit parameters
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
                temperature=temperature,  # Passed explicitly
                max_tokens=max_tokens,    # Passed explicitly
                model_kwargs=completion_params,  # Other parameters
                streaming=self.streaming,
            )
            # Azure OpenAI: handle response_format (compatible with both string and dict)
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
                # If it is a vision model, use the ChatOpenAI interface SDK; the ChatTongyi interface does not support it
                return ChatOpenAI(
                    base_url=os.environ['DASHSCOPE_ENDPOINT'],
                    api_key=os.environ['DASHSCOPE_KEY'],  # Can be any string
                    model=self.model.name,
                    temperature=temperature,  # Passed explicitly
                    max_tokens=max_tokens,    # Passed explicitly
                    model_kwargs=completion_params,  # Other parameters including response_format
                    streaming=self.streaming,
                    extra_body=extra_body
                    )
            # Tongyi Qianwen: response_format is passed directly via model_kwargs (already in dict format)
            return ChatTongyi(
                api_key=os.environ['DASHSCOPE_KEY'],
                base_url=os.environ['DASHSCOPE_ENDPOINT'],
                model=self.model.name,
                temperature=temperature,  # Passed explicitly
                max_tokens=max_tokens,    # Passed explicitly
                model_kwargs=completion_params,  # Other parameters including response_format
                streaming=self.streaming,
            )

    def get_model(self):
        """
        Get a LangChain-compatible LLM model instance

        For scenarios such as Agents that need direct access to the LLM model

        Returns:
            A LangChain LLM model instance (ChatTongyi or AzureChatOpenAI)
        """
        return self._determine_llm()