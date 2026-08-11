from goalflow.node.base import BaseNode,NodeOutput
from typing import Dict, Any, Optional, Literal, List, Mapping
from pydantic import BaseModel
from goalflow.workflow_types import Condition, LoopVariableData
from goalflow.state import GenericState
from goalflow.constants import WfNodeType,ErrorHandleMode
from langgraph.graph.state import CompiledStateGraph
from goalflow.tool.utils import VariableResolver
from goalflow.constants import STATE_VARIABLE_TYPE_OUTPUT,STATE_VARIABLE_TYPE_CONVERSATION
from goalflow.tool.condition.processor import ConditionProcessor
from langgraph.types import Command

LOOP_END_CALL_NAME = "loop-end-call"

class LoopStartNode(BaseNode):
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(**kwargs)
    
    def call(self, state: GenericState) -> NodeOutput:
        return Command(
            update={},
            goto=self.next_node_ids
        )
    
class LoopEndNode(BaseNode):
    """
    The sub-workflow must be forcibly exited when it reaches this node
    """
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(**kwargs)
    
    def call(self, state: GenericState) -> NodeOutput:
        """
        Loop end node
        """
        if self.loop_id is None:
            raise ValueError("loop id is None")
        
        update_data = VariableResolver.format_output(node_id=self.loop_id, outputs={LOOP_END_CALL_NAME:True})
    
        return Command(
            update=update_data,
            goto=self.next_node_ids
        )



class LoopNode(BaseNode):
    """
    Loop node for controlled iteration execution.
    This node executes a sub-workflow repeatedly until conditions are met or max iterations reached.
    """
    start_node_id: Optional[str] = None
    error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED
    loop_count: int  # Maximum number of loops
    break_conditions: List[Condition]  # Conditions to break the loop
    logical_operator: Literal["and", "or"]
    loop_variables: Optional[List[LoopVariableData]] = None
    outputs: Optional[Mapping[str, Any]] = None
    
    # read only
    __node_type = WfNodeType.LOOP
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(
        self, 
        *, 
        start_node_id: Optional[str] = None, 
        error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED,
        loop_count: int, 
        break_conditions: List[Condition],
        logical_operator: Literal["and", "or"], 
        loop_variables: Optional[List[LoopVariableData]] = None,
        outputs: Optional[Mapping[str, Any]] = None,
        subgraph: Optional[CompiledStateGraph] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.start_node_id = start_node_id
        self.error_handle_mode = error_handle_mode
        self.loop_count = loop_count
        self.break_conditions = break_conditions
        self.logical_operator = logical_operator
        self.loop_variables = loop_variables
        self.outputs = outputs
        self.subgraph = subgraph
    
    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute loop with the given state.
        """
        if self.subgraph is None:
            raise ValueError("iteration node subgraph is None")
        
        # Force it not to exceed 10
        if self.loop_count > 10:
            raise ValueError("loop count must be less than 10")
        
        loop_vars = {}
        for item in self.loop_variables:
            var_name = item.label
            value_type = item.value_type
            value = item.value
            if value_type == "variable":
                value = VariableResolver.resolve_value_selector(value,state)
            elif value_type == "constant":
                if item.var_type == "number" and isinstance(value, str):
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
            else:
                raise ValueError("loop var config error")
            
            selector = [self.id, var_name]
            key = "{}_{}".format(selector[0], selector[1])
            loop_vars[key] = value
            
        # Build the input for the sub-workflow
        subgraph_inputs = state.copy()
        subgraph_inputs[STATE_VARIABLE_TYPE_OUTPUT].update(loop_vars)

        self.condition_processor = ConditionProcessor()
                
        for i in range(self.loop_count):
            # Each loop needs to reset step to prevent multi-fan-in nodes from executing multiple times
            subgraph_inputs["step"] = 0
            # Execute the subgraph
            subgraph_inputs = self.subgraph.invoke(subgraph_inputs)
            # Check whether the break condition is met
            if self._check_break_conditions(subgraph_inputs):
                break
            
        conversation_vars = subgraph_inputs[STATE_VARIABLE_TYPE_CONVERSATION]   
        output_vars = subgraph_inputs[STATE_VARIABLE_TYPE_OUTPUT]   
        update_output_vars = {}
    
        # Only update the variables set by the loop node itself
        for key, value in output_vars.items():
            if key.startswith(self.id):
                update_output_vars[key] = value

        del subgraph_inputs, output_vars
        
        update_data:dict = VariableResolver.format_output(
            node_id=self.id, 
            src_node_id="conversation",
            outputs=conversation_vars,
            global_state_key=STATE_VARIABLE_TYPE_CONVERSATION
        )
        
        update_data.update({STATE_VARIABLE_TYPE_OUTPUT:update_output_vars})

        # Conversation variables set inside the loop need to be returned and updated into the outer state
        return Command(
            update=update_data,
            goto=self.next_node_ids
        )
    
    def _check_break_conditions(self, state: GenericState) -> bool:
        """
        Check if any break condition is met.
        param: state the output state of the sub-workflow
        """
        value = VariableResolver.resolve_value_selector([self.id, LOOP_END_CALL_NAME],state)
        
        if value :
            return True
        
        # If there is no loop termination condition, do not exit the loop by default
        if self.break_conditions is None or len(self.break_conditions) == 0:
            return False
        
        input_variables = state.get("input_variables" , {})
        output_variables = state.get("output_variables" , {})
        conversation_variables = state.get("conversation_variables" , {})

        variable_pool = {**input_variables, **output_variables, **conversation_variables}
        
        _, _, final_result = self.condition_processor.process_conditions(
            variable_pool= variable_pool,
            conditions=self.break_conditions,
            operator=self.logical_operator,
            state=state,
        )
        
        return final_result
