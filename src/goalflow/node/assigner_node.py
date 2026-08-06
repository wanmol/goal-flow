from goalflow.model.wf_conv_variable import WorkflowConversationVariables
from goalflow.node.base import BaseNode, NodeOutput
from typing import List, Optional, Dict, Any, Tuple
from goalflow.workflow_types import VariableOperationItem
from goalflow.service.workflow_conversation_variables_service import (
    WorkflowConversationVariablesService,
)
from goalflow.state import GenericState
from goalflow.constants import WfNodeType, AssignerInputType, AssignerOperation
from goalflow.tool.utils import VariableResolver

from langgraph.types import Command

import json


class AssignerNode(BaseNode):
    """
    Assigner node for variable assignments and operations.
    This node can assign, modify, and manipulate variables in the workflow state.
    """

    assignments: List[VariableOperationItem]

    # read only
    __node_type = WfNodeType.ASSIGNER

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(self, *, assignments: List[VariableOperationItem], **kwargs):
        super().__init__(**kwargs)
        self.assignments = assignments

    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute variable assignments with the given state.

        Args:
            state: Current workflow state

        Returns:
            Updated state with new variable assignments
        """
        try:
            conversation_variables, is_update_operation = (
                self._get_conversation_variables(state)
            )

            outputs = {}
            conversation_outputs = (
                conversation_variables if conversation_variables else {}
            )

            for assignment in self.assignments:
                target_var = assignment.variable_selector[
                    -1
                ]  # Last item is variable name

                # Resolve the value based on input type
                if assignment.input_type == AssignerInputType.CONSTANT:
                    value = assignment.value
                elif assignment.input_type == AssignerInputType.VARIABLE:
                    # assignment.value contains the source variable selector
                    if isinstance(assignment.value, list):
                        value = VariableResolver.resolve_value_selector(
                            assignment.value, state
                        )
                    else:
                        value = assignment.value
                else:
                    raise ValueError(f"Unsupported input type: {assignment.input_type}")

                # Apply the operation
                result_value = self._apply_operation(assignment, value, state)

                # Determine output destination
                if (
                    len(assignment.variable_selector) >= 2
                    and assignment.variable_selector[0] == "conversation"
                ):
                    conversation_outputs[target_var] = result_value
                else:
                    outputs[target_var] = result_value

            update_node_id = assignment.variable_selector[0]
            # Format outputs for state update
            final_outputs = {}
            if outputs:
                # print("=============assigner outputs:{}".format(outputs))
                output_update = VariableResolver.format_output(
                    node_id=self.id, src_node_id=update_node_id, outputs=outputs
                )
                final_outputs.update(output_update)

            if conversation_outputs:
                # print("=============assigner conversation_outputs:{}".format(conversation_outputs))
                conv_update = VariableResolver.format_output(
                    node_id=self.id,
                    src_node_id=update_node_id,
                    outputs=conversation_outputs,
                    global_state_key="conversation_variables",
                )
                final_outputs.update(conv_update)
                if is_update_operation:
                    WorkflowConversationVariablesService.update_by_conversation_id(
                        conv_vars=WorkflowConversationVariables(
                            conversation_id=self.conversation_id,
                            data=conversation_outputs,
                            last_updater_id=state.get("sys_user_id", ""),
                        )
                    )
                else:
                    WorkflowConversationVariablesService.create(
                        conversation_id=self.conversation_id,
                        data=conversation_outputs,
                        creator_id=state.get("sys_user_id", ""),
                    )
            return Command(update=final_outputs, goto=self.next_node_ids)

        except Exception as e:
            return self._handle_error(e)

    def _apply_operation(
        self, assignment: VariableOperationItem, value: Any, state: GenericState
    ) -> Any:
        """Apply the specified operation to the value."""
        operation = assignment.operation

        if operation == AssignerOperation.OVER_WRITE:
            return value
        elif operation == AssignerOperation.CLEAR:
            return (
                None
                if isinstance(value, (str, type(None)))
                else ([] if isinstance(value, list) else {})
            )
        elif operation == AssignerOperation.APPEND:
            # Get current value and append
            current = self._get_current_value(assignment.variable_selector, state)
            if isinstance(current, list):
                return current + [value]
            elif isinstance(current, str):
                return current + str(value)
            else:
                return [current, value] if current is not None else [value]
        elif operation == AssignerOperation.EXTEND:
            current = self._get_current_value(assignment.variable_selector, state)
            if isinstance(current, list) and isinstance(value, list):
                return current + value
            else:
                return value
        elif operation == AssignerOperation.SET:
            return value
        elif operation == AssignerOperation.ADD:
            current = self._get_current_value(assignment.variable_selector, state)
            return (current or 0) + (value or 0)
        elif operation == AssignerOperation.SUBTRACT:
            current = self._get_current_value(assignment.variable_selector, state)
            return (current or 0) - (value or 0)
        elif operation == AssignerOperation.MULTIPLY:
            current = self._get_current_value(assignment.variable_selector, state)
            return (current or 0) * (value or 1)
        elif operation == AssignerOperation.DIVIDE:
            current = self._get_current_value(assignment.variable_selector, state)
            return (current or 0) / (value or 1) if value != 0 else 0
        elif operation == AssignerOperation.REMOVE_FIRST:
            current = self._get_current_value(assignment.variable_selector, state)
            if isinstance(current, list) and current:
                return current[1:]
            return current
        elif operation == AssignerOperation.REMOVE_LAST:
            current = self._get_current_value(assignment.variable_selector, state)
            if isinstance(current, list) and current:
                return current[:-1]
            return current
        else:
            raise ValueError(f"Unsupported operation: {operation}")

    def _get_current_value(
        self, variable_selector: List[str], state: GenericState
    ) -> Any:
        """Get the current value of a variable from state."""
        try:
            return VariableResolver.resolve_value_selector(variable_selector, state)
        except:
            return None

    def _handle_error(self, e):
        """Handle errors based on error strategy."""
        if not self.error_strategy:
            raise e

        strategy_handlers = {
            "default-value": lambda: VariableResolver.format_output(
                node_id=self.id,
                outputs={dv.key: dv.value for dv in (self.default_value or [])},
            ),
            "fail-branch": lambda: Command(goto=self.fail_branch_node_ids),
        }

        handler = strategy_handlers.get(str(self.error_strategy))
        if not handler:
            raise ValueError(f"Invalid error strategy: {self.error_strategy}")

        return handler()

    def _get_conversation_variables(
        self, state: GenericState
    ) :
        """
        合并state和从数据库查询的conversation_variables
        state中已有的参数不会被覆盖

        Args:
            state: 当前工作流状态
        Returns:
            合并后的conversation_vars ,
            是否为更新操作
        """
        merged_conversation_vars = {}
        self.conversation_id = state.get("sys_conversation_id")
        # conversation_variables_obj: 从数据库查询的会话变量对象
        conversation_variables_obj = (
            WorkflowConversationVariablesService.get_by_conversation_id(
                conversation_id=self.conversation_id
            )
        )
        # 判断是修改还是新增
        is_update_operation = conversation_variables_obj is not None
        # 如果查询到了会话变量对象，则合并其data字段
        if conversation_variables_obj and hasattr(conversation_variables_obj, "data"):
            db_conversation_vars = conversation_variables_obj.data or {}

            if type(db_conversation_vars) == str:
                db_conversation_vars = json.loads(db_conversation_vars)

            # 获取state中现有的conversation_variables
            current_conversation_vars = state.get("conversation_variables", {})

            merged_conversation_vars.update(
                db_conversation_vars
            )  # 先添加数据库中的变量
            
            for key, value in current_conversation_vars.items():
                if key not in merged_conversation_vars or value:
                    merged_conversation_vars[key] = value
            
            # merged_conversation_vars.update(
            #     current_conversation_vars
            # )  # state中的变量覆盖数据库中的同名变量

        return merged_conversation_vars, is_update_operation
