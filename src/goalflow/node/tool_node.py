import time

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from goalflow.workflow_types import ToolProviderConfig, ToolProviderType, HttpNodeRetryConfig, \
    ToolParamSchema
from goalflow.node.base import BaseNode, NodeOutput
from typing import Dict, Any, Optional, Callable

from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.utils import VariableResolver
import json

from goalflow.config import get_logger

logger = get_logger(__name__)


class ToolNode(BaseNode):
    """
    Tool node for external tool integration.
    This node executes external tools and processes their outputs.
    """
    # read only
    __node_type = WfNodeType.TOOL

    is_team_authorization: bool = True,
    output_schema = None,
    param_schema: Optional[list[ToolParamSchema]] = None,

    tool_provider_config: ToolProviderConfig = None
    func: Callable = None

    retry_config: Optional[HttpNodeRetryConfig] = None

    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type

    def __init__(self, *,
                 is_team_authorization: bool = True,
                 output_schema=None,
                 param_schemas: Optional[list[ToolParamSchema]] = None,

                 tool_provider_config: ToolProviderConfig = None,
                 func: Callable = None,
                 retry_config: Optional[HttpNodeRetryConfig] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.is_team_authorization = is_team_authorization
        self.output_schema = output_schema
        self.param_schemas = param_schemas

        self.tool_provider_config = tool_provider_config
        self.func = func
        self.retry_config = retry_config

        # Precompute retry parameters to avoid recomputing on each execution
        self._precompute_retry_config()

        # Precompile error handlers to improve error handling efficiency
        self._error_handlers = {
            "default-value": self._handle_default_value_error,
            "fail-branch": self._handle_fail_branch_error
        }

    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute the external tool with the given state.
        """
        try:

            # Variable pool
            variable_pool = self._merge_variables(state)
            # The processed result must be a dict structure
            outputs = self._execute_with_retry(variable_pool, state)

            result = VariableResolver.format_output(
                    node_id=self.id,
                    outputs = outputs
            )

            return Command(
                update=result,
                goto=self.next_node_ids
            )
        except Exception as e:
            logger.error(f"tool node error: {e}",exc_info=True,  node_id=self.formatted_name)

            return self._handle_error(e)

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

    def _handle_default_value_error(self) -> Command:
        """Default value error handling"""
        default_text = self.default_value[0]['value'] if self.default_value else ''
        return Command(
            update=VariableResolver.format_output(
                node_id=self.id,
                outputs={"text": default_text}
            ),
            goto=self.next_node_ids
        )

    def _handle_fail_branch_error(self) -> Command:
        """Fail branch error handling"""
        return Command(update={},goto=self.fail_branch_node_ids)

    def _handle_error(self, e):
        if not self.error_strategy:
            raise e

        # Use the precompiled error handlers
        handler = self._error_handlers.get(self.error_strategy)
        if not handler:
            raise ValueError(f"Invalid error strategy: {self.error_strategy}")
        return handler()

    def _workflow_processor(self, variable_pool: dict[str, Any], state: GenericState) -> NodeOutput:
        """
        Process the sub-workflow
        """
        if not self.tool_provider_config or not self.tool_provider_config.tool_parameters:
            return {}

        result = {}
        tool_parameters = self.tool_provider_config.tool_parameters

        # Group by parameter type to reduce repeated conditional checks
        constant_params = {}
        mixed_params = {}
        variable_params = {}

        for key, param_config in tool_parameters.items():
            param_type = param_config.type
            if param_type == "constant":
                constant_params[key] = param_config.value
            elif param_type == "mixed":
                mixed_params[key] = param_config.value
            elif param_type == "variable":
                variable_params[key] = param_config.value
            else:
                raise ValueError(f"Invalid tool processor type: {param_type}")

        # Batch process constant parameters
        result.update(constant_params)

        # Batch process template parameters
        for key, template in mixed_params.items():
            result[key] = None if template is None else VariableResolver.replace_template(template, state)

        # Batch process variable parameters
        for key, value_selector in variable_params.items():
            result[key] = VariableResolver.resolve_value_selector(value_selector, state)

        return result

    def _precompute_retry_config(self):
        """
        Precompute the retry configuration parameters
        """
        self._max_retries = 0
        self._retry_interval = 1.0
        self._retry_enabled = False

        if self.retry_config:
            self._max_retries = getattr(self.retry_config, "max_retries", 0)
            self._retry_interval = getattr(self.retry_config, 'retry_interval', 100) / 1000.0
            self._retry_enabled = getattr(self.retry_config, 'retry_enabled', False)

            if not self._retry_enabled:
                self._max_retries = 0

    def _execute_single_attempt(self, variable_pool: dict[str, Any], state: GenericState):
        """
        Single execution attempt
        """
        if self.tool_provider_config:
            if self.tool_provider_config.provider_type == ToolProviderType.WORKFLOW:
                # Process the workflow
                wf_input = self._workflow_processor(variable_pool, state)

                logger.info(f"tool node {self.formatted_name} sub workflow input : {wf_input}", node_id=self.formatted_name)
                
                wf_input = {"input_variables" : wf_input}
                
                if not self.func:
                    logger.error(f"tool node {self.formatted_name} sub workflow error : func can't be None.", node_id=self.formatted_name)
                    raise ValueError("func can't be None.")
                
                result = self.func(wf_input)

                logger.info(f"tool node {self.formatted_name} sub workflow result : {result}", node_id=self.formatted_name)

                if "outputs" in result:
                    result = result["outputs"]
                else:
                    raise ValueError("tool node result not outputs!!!")
                outputs={"text": json.dumps(result, ensure_ascii=False),
                             "json": [result]}
                return outputs
            elif self.tool_provider_config.provider_type == ToolProviderType.BUILT_IN and (self.tool_provider_config.tool_name == "parse" or self.tool_provider_config.tool_name == "tavily_search"):

                _tool_parameters = {}
                for param_schema in self.param_schemas:
                    tool_parameters = self.tool_provider_config.tool_parameters

                    _tool_parameters[param_schema.name] = param_schema.default if not tool_parameters.get(
                        param_schema.name, "") else tool_parameters.get(param_schema.name).to_json()

                #function_response = self.func(**tool_parameters)

                # json-ng parse json
                function_response = self.func(
                     tool_parameters=_tool_parameters,
                     variable_pool=state,
                )
                # result = json_parser.parse()
                outputs={
                    "text": function_response,
                    "files": [],
                    "json": None
                }
                return outputs

        else:
            raise NotImplementedError(f"Provider type {self.tool_provider_config} not implemented")

            # Implement json parsing
            # TODO: implement other provider types
            raise NotImplementedError(f"Provider type {self.tool_provider_config.provider_type} not implemented")

    def _execute_with_retry(self, variable_pool: dict[str, Any], state: GenericState) -> dict[str, Any] | Any:
        """
        Retryable see http_request_node.py
        """
        # Fast path: execute directly when there are no retries
        if self._max_retries == 0:
            return self._execute_single_attempt(variable_pool, state)

        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._execute_single_attempt(variable_pool, state)
            except Exception as e:
                last_exception = e

                # Fast fail: certain errors should not be retried
                if self._is_non_retryable_error(e):
                    raise e

                if attempt < self._max_retries:
                    # Exponential backoff algorithm
                    backoff_time = self._retry_interval * (2 ** attempt)
                    time.sleep(min(backoff_time, 30))  # Maximum backoff of 30 seconds
                else:
                    raise e

        raise last_exception

    def _is_non_retryable_error(self, error: Exception) -> bool:
        """
        Determine whether the error is non-retryable
        """
        # Configuration errors, parameter errors, etc. should not be retried
        non_retryable_errors = (ValueError, TypeError, AttributeError, KeyError)
        return isinstance(error, non_retryable_errors)
