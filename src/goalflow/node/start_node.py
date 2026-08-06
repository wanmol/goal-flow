from goalflow.node.base import BaseNode,NodeOutput
from typing import Optional, List
from pydantic import BaseModel
from goalflow.workflow_types import WfVariableConfig
from goalflow.state import BaseState,GenericState
from goalflow.constants import (
    WfNodeType,
    STATE_VARIABLE_TYPE_CONVERSATION
)
from goalflow.tool.utils import VariableResolver
import time
from langgraph.types import Command
from goalflow.service.workflow_conversation_variables_service import (
    WorkflowConversationVariablesService,
)
import json

from goalflow.config import get_logger

logger = get_logger(__name__)

class StartNode(BaseNode):
    """
    Start node for workflow execution.
    This node initializes the workflow state with input variables.
    """
    wf_inputs: List[WfVariableConfig]
    
    # read only
    __node_type = WfNodeType.START
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(self, *, wf_inputs: List[WfVariableConfig], **kwargs):
        super().__init__(**kwargs)
        self.wf_inputs = wf_inputs
    
    # TODO  需要处理conversation_id,workflow_id,workflow_run_id等
    def call(self, state: GenericState) -> NodeOutput:
        """
        Initialize workflow state with input variables.
        The start node typically receives input from the user and sets up the initial state.
        """

        # Create a copy of state for logging and remove financial_data to reduce log size
        # state_for_log = state.copy()
        # if isinstance(state_for_log.get("input_variables"), dict):
        #     state_for_log["input_variables"] = state_for_log["input_variables"].copy()
        #     state_for_log["input_variables"].pop("financial_data", None)
        # logger.info(f"start node input state: {state_for_log}", node_id=self.formatted_name)
        logger.info(f"start node input state: {state}", node_id=self.formatted_name)

        #input_variables was assgined when stategraph invoked, here just check it
        input_variables = state.get("input_variables",{})
        for input in self.wf_inputs:
            if input.required and input.variable not in input_variables:
                raise ValueError(f"Required input variable {input.variable} not provided")
            
            if input.type == "select" :
                if "options" not in input or not input.options :
                    raise ValueError(f"Input variable {input.variable} must have options")
                
            if input.variable not in input_variables:
                # 处理默认值
                if input.default is not None:
                    input_variables[input.variable] = input.default
                continue
            
            value = input_variables[input.variable]
            if input.type == "number" and value is not None and not isinstance(value, (int, float)):
                raise ValueError(f"Input variable {input.variable} must be a number")
            if input.type == "array[number]" and not all(isinstance(v, (int, float)) for v in value):
                 raise ValueError(f"Input variable {input.variable} must be a number array")
            if input.type == "file" and not isinstance(value, dict):
                    raise ValueError(f"Input variable {input.variable} must be a file")
            if input.type in ("text-input","paragraph") and value is not None and not isinstance(value, str):
                raise ValueError(f"Input variable {input.variable} must be a string")
            if input.type == "array[file]" and not all(isinstance(v, dict) for v in value):
                raise ValueError(f"Input variable {input.variable} must be a file array")

        # dify中间节点取query 等系统变量时，会拼上开始节点前缀
        outputs = {"sys.query" : state.get("sys_query")}
        # 需要将用户的输入更新到开始节点， dify配置文件中后续节点访问用户输入是带开始节点前缀的
        outputs.update(input_variables)

        # 从数据库查询会话变量，初始化state中的conversation_variables
        conversation_vars = {}
        conversation_id = state.get("sys_conversation_id")
        if conversation_id is not None:
            conversation_vars = self._get_conversation_variables(state,conversation_id)
        
        conversation_variables = {STATE_VARIABLE_TYPE_CONVERSATION: conversation_vars}
        
        update:dict = VariableResolver.format_output(node_id=self.id,outputs=outputs)
        
        update.update(conversation_variables)
        
        return Command(
            update=update,
            goto=self.next_node_ids
        )
        
    def _get_conversation_variables(
        self, state: GenericState,
        conversation_id: str ,
    ) :
        """
        从数据库查询的conversation_variables

        Args:
            state: 当前工作流状态
        Returns:
            conversation_vars ,
        """
        conversation_vars = {}
        
        # conversation_variables_obj: 从数据库查询的会话变量对象
        conversation_variables_obj = (
            WorkflowConversationVariablesService.get_by_conversation_id(
                conversation_id=conversation_id
            )
        )
        if conversation_variables_obj and hasattr(conversation_variables_obj, "data"):
            conversation_vars = conversation_variables_obj.data or {}

            if type(conversation_vars) == str:
                conversation_vars = json.loads(conversation_vars)
                
        return conversation_vars  
    
    # 如果output太长， 某些日志系统，比如阿里云sls会截断日志信息，导致json结构被破坏，不好做数据分析
    def truncate_output_value(self, value : any) :
        if not value:
            return value
        
        if isinstance(value, str):
            return value[:1000]
        
        result = {}
        for key in value:
            # 会话变量可能会很长，需要截断处理。仅仅输出log截断
            if key != STATE_VARIABLE_TYPE_CONVERSATION:
                result[key] = value[key]
                
        return result
