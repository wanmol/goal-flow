from goalflow.node.base import BaseNode, NodeOutput
from typing import Optional, Dict, Sequence, List, Generic, Any
from pydantic import BaseModel
from goalflow.workflow_types import (
    LLMNodeModelConfig,
    QuestionClassConfig,
    MemoryConfig,
    LLmNodePromptTemplate,
)
from goalflow.state import GenericState
from goalflow.constants import WfNodeType, PromptMessageRole
from goalflow.prompts import *
from goalflow.llm import LLM
import json
from goalflow.tool.utils import VariableResolver
from langgraph.types import Command

from goalflow.config import get_logger

logger = get_logger(__name__)


class ClassifierNode(BaseNode):
    instruction: Optional[str] = None
    query_variable_selector: Sequence[str]
    model: LLMNodeModelConfig
    memory: Optional[MemoryConfig] = None
    vision: Optional[Dict] = None
    classes: list[QuestionClassConfig]

    # read only
    __node_type = WfNodeType.QUESTION_CLASSIFIER

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(
        self,
        *,
        instruction: Optional[str] = None,
        classes: list[QuestionClassConfig] = None,
        query_variable_selector: Sequence[str] = None,
        model: LLMNodeModelConfig = None,
        memory: Optional[MemoryConfig] = None,
        vision: Optional[Dict] = None,
        source_handle_target_map: Optional[Dict[str, List[str]]] = {},
        **kwargs,
    ):

        super().__init__(**kwargs)

        self.instruction = instruction
        self.classes = classes
        self.query_variable_selector = query_variable_selector
        self.model = model
        self.memory = memory
        self.vision = vision
        self.source_handle_target_map = source_handle_target_map

    def call(self, state: GenericState) -> NodeOutput:
        """implements protocol _StateNode"""

        input_text = ""
        if self.query_variable_selector and self.query_variable_selector != "":
            input_text = VariableResolver.resolve_value_selector(
                self.query_variable_selector, state
            )

        if input_text == "" or input_text is None:
            input_text = state.get("sys_query")

        prompt_templates = self._get_prompt_template(input_text)

        llm = LLM(
            context=None,
            prompt_template=prompt_templates,
            memory=self.memory,
            model=self.model,
            vision=self.vision,
            state=state,
            streaming=False,
            disable_streaming=True,
            node_id=self.formatted_name,
            llm_node=self
        )
        
        content = None
        try:
            content: str = llm.invoke().content
        except Exception as e:
            logger.error(f"classifier invoke llm error: {e}",  node_id=self.formatted_name)
            raise e
        
        result = None
        try:
            result = json.loads(
                content.replace("```json", "").replace("```", "").strip()
            )
        except Exception as e:
            logger.error(f"classifier invoke llm no json result: {content}",  node_id=self.formatted_name)
            raise ValueError(f"classifier invoke llm no json result: {content}")

        if isinstance(result, list):
            result = result[0]

        category_name = result.get("category_name")
        if not category_name:
            logger.error(f"classifier invoke llm no category_name result: {content}",  node_id=self.formatted_name)
            raise ValueError(
                f"classifier invoke llm no category_name result: {content}"
            )

        category = next((c for c in self.classes if c.name == category_name), None)
        if not category:
            logger.error(f"classifier invoke llm no category result: {content}",  node_id=self.formatted_name)
            raise ValueError(f"classifier invoke llm no category result: {content}")

        logger.info(f"{self.formatted_name} selected question class: {category.name}")

        target_node_ids = self.source_handle_target_map.get(category.id)
        if not target_node_ids:
            logger.error(f"classifier invoke llm no target_node_ids result: {content}",  node_id=self.formatted_name)
            raise ValueError(
                f"classifier invoke llm no target_node_ids result: {content}"
            )
        
        outputs  = {"class_name": category.name, "category_id": category.id}
        update_data = VariableResolver.format_output(node_id=self.id, outputs=outputs)
        update_data["source_handle"] = category.id
        return Command(
            update=update_data,
            goto=target_node_ids,
        )

    def _get_prompt_template(self, input_text: str) -> Sequence[LLmNodePromptTemplate]:
        categories = []
        for class_ in self.classes:
            category = {"category_id": class_.id, "category_name": class_.name}
            categories.append(category)
        instruction = self.instruction or ""

        prompt_messages: list[LLmNodePromptTemplate] = []

        # TODO history messages still to be handled
        system_prompt_messages = LLmNodePromptTemplate(
            role=PromptMessageRole.SYSTEM.value,
            text=QUESTION_CLASSIFIER_SYSTEM_PROMPT.format(histories=""),
        )
        prompt_messages.append(system_prompt_messages)
        user_prompt_message_1 = LLmNodePromptTemplate(
            role=PromptMessageRole.USER.value, text=QUESTION_CLASSIFIER_USER_PROMPT_1
        )
        prompt_messages.append(user_prompt_message_1)
        assistant_prompt_message_1 = LLmNodePromptTemplate(
            role=PromptMessageRole.ASSISTANT.value,
            text=QUESTION_CLASSIFIER_ASSISTANT_PROMPT_1,
        )
        prompt_messages.append(assistant_prompt_message_1)
        user_prompt_message_2 = LLmNodePromptTemplate(
            role=PromptMessageRole.USER.value, text=QUESTION_CLASSIFIER_USER_PROMPT_2
        )
        prompt_messages.append(user_prompt_message_2)
        assistant_prompt_message_2 = LLmNodePromptTemplate(
            role=PromptMessageRole.ASSISTANT.value,
            text=QUESTION_CLASSIFIER_ASSISTANT_PROMPT_2,
        )
        prompt_messages.append(assistant_prompt_message_2)
        user_prompt_message_3 = LLmNodePromptTemplate(
            role=PromptMessageRole.USER.value,
            text=QUESTION_CLASSIFIER_USER_PROMPT_3.format(
                input_text=input_text,
                categories=json.dumps(categories, ensure_ascii=False),
                classification_instructions=instruction,
            ),
        )
        prompt_messages.append(user_prompt_message_3)
        return prompt_messages
