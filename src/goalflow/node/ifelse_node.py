from goalflow.node.base import BaseNode, NodeOutput
from typing import Dict, Any, Optional, Literal, List, Sequence

from goalflow.workflow_types import Condition, SubVariableCondition, SubCondition, Case
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.condition.processor import ConditionProcessor
from langgraph.types import Command

from goalflow.config import get_logger

logger = get_logger(__name__)

class IfElseNode(BaseNode):
    """
    Conditional logic node for workflow branching.
    This node evaluates conditions and determines the execution path.
    """
    logical_operator: Optional[Literal["and", "or"]] = "and"
    conditions: Optional[List[Condition]] = None
    cases: Optional[List[Dict[str, Any]]] = None

    # read only
    __node_type = WfNodeType.IF_ELSE

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(self, *, logical_operator: Optional[Literal["and", "or"]] = "and",
                 conditions: Optional[List[Condition]] = None,
                 cases: Optional[List[Case]] = None,
                 source_handle_target_map: Optional[Dict[str, List[str]]] = {},
                 **kwargs):
        super().__init__(**kwargs)
        self.logical_operator = logical_operator
        self.conditions = conditions
        self.cases = cases
        self.source_handle_target_map = source_handle_target_map

    def call(self, state: GenericState) -> NodeOutput:
        """
        Evaluate conditions and determine the execution path.
        """

        # Prepare the input data record
        node_inputs: dict[str, list] = {"conditions": []}
        # Prepare the processing data record
        process_data: dict[str, list] = {"condition_results": []}

        input_conditions = []  # Store the original condition statements
        final_result = False  # Final evaluation result
        selected_case_id = None  # ID of the matched condition branch
        condition_processor = ConditionProcessor()  # Condition processor

        variable_pool = self._merge_variables(state)

        selected_case_id = "false"

        for case in self.cases:
            input_conditions, group_result, final_result = condition_processor.process_conditions(
                variable_pool=variable_pool,
                conditions=case.conditions,
                operator=case.logical_operator,
                state=state,
            )
            process_data["condition_results"].append(
                {
                    # "group": case.model_dump(),
                    "results": group_result,
                    "final_result": final_result,
                }
            )

            # Break if a case passes (logical short-circuit)
            if final_result:
                selected_case_id = case.case_id  # Capture the ID of the passing case
                break
        # print("selected branch", selected_case_id)
        next_ids = self.source_handle_target_map.get(selected_case_id, [])
        if next_ids == []:
            next_ids = ['false']

        
        #print("if else node finished!, selected_next_ids:{}".format(next_ids))
        logger.info(f"{self.formatted_name} node finished!", selected_next_ids=next_ids)

        return Command(
            update={"node_id": self.id, "source_handle": selected_case_id},
            goto=next_ids
        )

    def _merge_variables(self, state: GenericState) -> Dict[str, Any]:
        """
        Build the variable pool using an efficient dict merge
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
        # Using dict.update() is more efficient than dict unpacking
        variable_pool.update(state.get("input_variables", {}))
        variable_pool.update(state.get("output_variables", {}))
        variable_pool.update(state.get("conversation_variables", {}))
        return variable_pool
