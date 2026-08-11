"""
Utility functions for workflow execution and state management.
"""

from typing import Any, Dict, List, Optional,Literal, TypeVar
from goalflow.state import GenericState
import re
from goalflow.constants import (
    STATE_VARIABLE_TYPE,
    STATE_VARIABLE_TYPE_CONVERSATION,
    STATE_VARIABLE_TYPE_ENVIRONMENT,
    STATE_VARIABLE_TYPE_INPUT,
    STATE_VARIABLE_TYPE_OUTPUT,
)

from goalflow.config import get_logger

logger = get_logger(__name__)

MIN_SELECTORS_LENGTH = 2

class VariableResolver:
    """
    Utility class for resolving variables in workflow states.
    """
    
    @classmethod
    def resolve_value_selector(cls,value_selector: List[str], state: GenericState) -> Any:
        """
        Resolve a value selector to its actual value in the state.
        
        Args:
            value_selector: List containing [node_id, variable_name]
            state: The current workflow state
            
        Returns:
            The resolved value or None if not found
        """
        if not value_selector or len(value_selector) < MIN_SELECTORS_LENGTH:
            raise ValueError("Invalid selector")
        
        #node_id, variable_name = value_selector
        node_id = value_selector[0]
        variable_name = value_selector[-1]
        
        # Handle system variables
        if node_id == 'sys':
            return state.get(f'sys_{variable_name}', None)
        
        if node_id == 'env':
            env_vars = state.get(STATE_VARIABLE_TYPE_ENVIRONMENT, {})
            return env_vars.get(variable_name, None)
        
        if node_id == 'conversation':
            conversation_vars = state.get(STATE_VARIABLE_TYPE_CONVERSATION, {})
            return conversation_vars.get(variable_name, None)
        
        hash_key = cls._selector_to_key(value_selector)
        # Handle conversation variables
        
        # Handle output variables from other nodes
        output_vars = state.get(STATE_VARIABLE_TYPE_OUTPUT, {})
        
        # Try node-specific variable first
        if hash_key in output_vars:
            return output_vars[hash_key]
        
        # Try direct variable name
        if variable_name in output_vars:
            return output_vars[variable_name]
        
        # Try in the main state
        if variable_name in state:
            return state[variable_name]
            
        return None
    
    @classmethod
    def _selector_to_key(cls,selector: List[str]) -> str:
        return "_".join(selector)
        #return "{}_{}".format(selector[0], hash(tuple(selector[1:])))
    
    
    @classmethod
    def format_output(
        cls,
        *,
        node_id:str , 
        outputs:dict[str,any],
        src_node_id: Optional[str] = None,
        global_state_key:str = STATE_VARIABLE_TYPE_OUTPUT,
    ) -> None:
        if outputs is None:
            return None
        
        if global_state_key not in [STATE_VARIABLE_TYPE_INPUT, STATE_VARIABLE_TYPE_OUTPUT, STATE_VARIABLE_TYPE_CONVERSATION]:
            raise ValueError(f"Invalid variables_type: {global_state_key}")
        
        if src_node_id is None:
            src_node_id = node_id
        
        final_result = {} 
        for key, value in outputs.items():
            selector=[src_node_id,key]

            if src_node_id == 'conversation':
                selector = [key]

            cls._format_output_recursively(
                selector=selector,
                output=value, 
                result=final_result
            )
           
        return {global_state_key:final_result,"node_id":node_id,"source_handle":"source"}        

    
    @classmethod
    def _format_output_recursively(
        cls,
        *,
        selector:list[str] , 
        output:any,
        result:dict[str,any]
    ):
        
        hash_key = cls._selector_to_key(selector)
        result[hash_key] = output
            
        if isinstance(output, dict):
            for key, value in output.items():
                cls._format_output_recursively(
                    selector=selector + [key], 
                    output=value, 
                    result=result
                )

    @staticmethod
    def resolve_template_string(template: str, variables: Dict[str, Any], state: GenericState) -> str:
        """
        Resolve template variables in a string.
        
        Args:
            template: Template string with variables in {{#variable#}} format
            variables: Dictionary of resolved variables
            state: Current workflow state
            
        Returns:
            String with variables resolved
        """
        def replace_var(match):
            var_ref = match.group(1)
            
            # Handle system variables like sys.query
            if var_ref.startswith('sys.'):
                sys_var = var_ref[4:]  # Remove 'sys.' prefix
                return str(state.get(f'sys_{sys_var}', ''))
            
            # Handle conversation variables
            if var_ref.startswith('conversation.'):
                conv_var = var_ref[13:]  # Remove 'conversation.' prefix
                return str(state.get(f'conversation_{conv_var}', ''))
            
            # Handle node output variables like node_id.variable_name
            if '.' in var_ref:
                parts = var_ref.split('.')
                if len(parts) == 2:
                    node_id, var_name = parts
                    output_vars = state.get('output_variables', {})
                    node_var_key = f'{node_id}_{var_name}'
                    value = output_vars.get(node_var_key, output_vars.get(var_name, ''))
                    return str(value)
            
            # Handle resolved variables
            if var_ref in variables:
                return str(variables[var_ref])
            
            # Handle direct state variables
            if var_ref in state:
                return str(state[var_ref])
                
            return match.group(0)  # Return original if not found
        
        # Replace variables in the format {{#variable#}}
        pattern = r'\{\{#([^#]+)#\}\}'
        return re.sub(pattern, replace_var, template)
    
    @staticmethod
    def resolve_variables_from_config(variables_config: List, state: GenericState) -> Dict[str, Any]:
        """
        Resolve all variables from a node's variable configuration.
        
        Args:
            variables_config: List of NodeVarConfig objects
            state: Current workflow state
            
        Returns:
            Dictionary of resolved variables
        """
        resolved = {}
        
        if variables_config:
            for var_config in variables_config:
                variable_name = var_config.variable
                value_selector = var_config.value_selector
                
                resolved_value = VariableResolver.resolve_value_selector(value_selector, state)
                resolved[variable_name] = resolved_value
        
        return resolved

    @staticmethod
    def replace_template(template: str, variables: dict):
        """
           Handle replacement of variable names that contain spaces
           Supports various space combinations: {{# var #}}, {{#var#}}, {{#  var  #}}, etc.

           Args:
               template: Template containing {{#variable#}} format
               variables: Dictionary mapping variable names to values

           Returns:
               The string after replacement
           """
        # Regex improvement: match cases containing spaces
        pattern = r'\{\{\#\s*([^\}#]+?)\s*\#\}\}'

        # Callback function that performs the replacement
        def replace_match(match):
            # Extract the variable name and strip surrounding spaces
            raw_var_name = match.group(1).strip()
            selector = raw_var_name.split(".")
            data = VariableResolver.resolve_value_selector(selector, variables)
            # Handle empty values
            if data is None or data == [] or data == "":
                return ""
            # TODO
            return str(data)

        # Replace using the regex
        try:
            return re.sub(pattern, replace_match, template)
        except Exception as e:
            logger.error(f"replace_template error: {e}", exc_info=True)
            raise e


class StateManager:
    """
    Utility class for managing workflow state.
    """
    
    @staticmethod
    def ensure_output_variables(state: GenericState) -> GenericState:
        """
        Ensure the state has an output_variables dictionary.
        
        Args:
            state: Current workflow state
            
        Returns:
            State with output_variables initialized
        """
        if 'output_variables' not in state:
            state['output_variables'] = {}
        return state
    
    @staticmethod
    def add_node_output(state: GenericState, node_id: str, outputs: Dict[str, Any]) -> GenericState:
        """
        Add node outputs to the state.
        
        Args:
            state: Current workflow state
            node_id: ID of the node producing the output
            outputs: Dictionary of output variables
            
        Returns:
            Updated state
        """
        state = StateManager.ensure_output_variables(state)
        
        for key, value in outputs.items():
            state['output_variables'][f'{node_id}_{key}'] = value
        
        return state
    
    @staticmethod
    def get_node_output(state: GenericState, node_id: str, output_name: str, default: Any = None) -> Any:
        """
        Get a specific output from a node.
        
        Args:
            state: Current workflow state
            node_id: ID of the node
            output_name: Name of the output variable
            default: Default value if not found
            
        Returns:
            The output value or default
        """
        output_vars = state.get('output_variables', {})
        node_var_key = f'{node_id}_{output_name}'
        
        return output_vars.get(node_var_key, output_vars.get(output_name, default))
    
    @staticmethod
    def merge_states(base_state: GenericState, update_state: GenericState) -> GenericState:
        """
        Merge two states, with update_state taking priority.
        
        Args:
            base_state: Base state
            update_state: State with updates
            
        Returns:
            Merged state
        """
        merged = base_state.copy()
        merged.update(update_state)
        
        # Merge output_variables separately
        if 'output_variables' in base_state and 'output_variables' in update_state:
            merged_outputs = base_state['output_variables'].copy()
            merged_outputs.update(update_state['output_variables'])
            merged['output_variables'] = merged_outputs
        
        return merged