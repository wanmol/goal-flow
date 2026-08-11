from goalflow.node.base import BaseNode ,NodeOutput
from pydantic import BaseModel
from typing import Optional
from goalflow.workflow_types import AggregatorAdvancedSettings
from goalflow.state import GenericState
from goalflow.tool.utils import VariableResolver

from langgraph.graph.state import Command


class AggregatorNode(BaseNode):
    """
    Aggregator node for workflow aggregation.
    This node aggregates the results of multiple nodes.
    """
    output_type: str
    variable_selectors: list[list[str]]
    advanced_settings: Optional[AggregatorAdvancedSettings] = None
    
    def __init__(self,*,output_type: str,variable_selectors: list[list[str]],
                 advanced_settings: Optional[AggregatorAdvancedSettings] = None,**kwargs):
        super().__init__(**kwargs)
        self.output_type = output_type
        self.variable_selectors = variable_selectors
        self.advanced_settings = advanced_settings
        
    def call(self,state:GenericState) -> NodeOutput:
        """
        Implements protocol _StateNode
        Aggregate variables depending on whether grouping is enabled:
        - Not grouped: find the first non-null value in variable_selectors, return {"output": result}
        - Grouped: iterate each group, apply the same logic per group, return {"group_name": {"output": result}}
        """
        outputs = {}

        # Check whether grouping is enabled
        if not self.advanced_settings or not self.advanced_settings.group_enabled:
            # Non-grouped mode: iterate variable_selectors, find the first non-null value
            for selector in self.variable_selectors:
                variable_value = VariableResolver.resolve_value_selector(selector, state)
                if variable_value is not None:
                    outputs["output"] = variable_value
                    break
        else:
            # Grouped mode: iterate each group
            for group in self.advanced_settings.groups:
                for selector in group.variables:
                    variable_value = VariableResolver.resolve_value_selector(selector, state)
                    if variable_value is not None:
                        outputs[group.group_name] = {"output": variable_value}
                        break
        
        update = VariableResolver.format_output(node_id=self.id,outputs=outputs)
        return Command(
            update=update,
            goto=self.next_node_ids
        )
