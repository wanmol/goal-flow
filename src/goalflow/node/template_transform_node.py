from goalflow.workflow_types import NodeVarConfig
from goalflow.node.base import BaseNode, NodeOutput
from typing import Dict, Any, Optional, Sequence
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.utils import VariableResolver
from jinja2 import Template
import time
from langgraph.types import Command

class TemplateTransformNode(BaseNode):
    """
    Template transform node for text processing and transformation.
    This node applies template transformations to text using variables from the workflow state.
    """
    template: str
    variables: Sequence[NodeVarConfig] = None

    # read only
    __node_type = WfNodeType.TEMPLATE_TRANSFORM
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    def __init__(self, *, template: str, **kwargs):
        super().__init__(**kwargs)
        self.template = template
        #self.variables = variables
    
    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute template transformation with the given state.
        
        Args:
            state: Current workflow state
            
        Returns:
            Transformed text output
        """
        
        result_dict_parse = {}
        if self.variables:
            for var1 in self.variables:
                result_dict_parse[var1.variable] = VariableResolver().resolve_value_selector(var1.value_selector, state)

        # Render the template
        tpl = Template(self.template)
        rendered = tpl.render(result_dict_parse)
        # print(rendered)
        output = VariableResolver.format_output(
            node_id = self.id,
            outputs={"output": rendered}
        )

        return Command(
            update=output,
            goto=self.next_node_ids
        )
