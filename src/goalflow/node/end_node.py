from goalflow.node import BaseNode,NodeOutput
from goalflow.constants import WfNodeType
from typing import Dict
from goalflow.workflow_types import NodeVarConfig
from goalflow.state import BaseState,GenericState
from goalflow.tool.utils import VariableResolver

class EndNode(BaseNode):
    """
    End node for workflow execution.
    """
    outputs: list[NodeVarConfig]
    
    # read only
    __node_type = WfNodeType.END
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(
        self, 
        *, 
        outputs: list[NodeVarConfig], 
        **kwargs
    ):
        super().__init__(**kwargs)
        self.outputs = outputs

    def call(self, state: BaseState) -> NodeOutput:
        output_variables = self.outputs

        outputs = {}
        for variable_selector in output_variables:
            variable = VariableResolver.resolve_value_selector(variable_selector.value_selector,state)
            value = variable if variable is not None else None
            outputs[variable_selector.variable] = value

        # Set the outputs variable that is emitted when the workflow ends in the state
        return {"outputs":outputs}
