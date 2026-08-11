from goalflow.node.base import BaseNode,NodeOutput
from typing import Dict, Any, Optional
from pydantic import BaseModel
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.utils import VariableResolver
from langgraph.graph.state import Command

from goalflow.config import get_logger

logger = get_logger(__name__)

class CodeNode(BaseNode):
    """
    Code execution node for running Python code.
    This node executes Python code with access to workflow variables.
    """
    code: str
    code_language: str
    outputs: Dict[str, Dict[str, str]]
    output_vars: Dict[str, str]
    
    # read only
    __node_type = WfNodeType.CODE
    
    @property
    def node_type(self) -> WfNodeType:
        return self.__node_type
    
    # TODO: support passing an external function directly (for manual flow orchestration)
    def __init__(self, *, code: str, code_language: str, outputs: Dict[str, Dict[str, str]], **kwargs):
        super().__init__(**kwargs)
        self.code = code
        self.code_language = code_language
        self.outputs = outputs

        # Extract output variable types
        self.output_vars = {}
        for var_name, var_config in outputs.items():
            self.output_vars[var_name] = var_config.get('type', 'string')
    
    
    def call(self, state: GenericState) -> NodeOutput:
        """
        Execute the code with the given state.
        Dynamically executes Python code, reading variables from state and returning the result.
        """

        #print(state)
        
        logger.info(f"{self.formatted_name} code node process",code=self.code)
        #print(repr(self.code))
        #self.code = repr(self.code)

        import traceback

        try:
            # 1. Prepare the execution environment and variables
            execution_context = self._prepare_execution_context(state)

            # 2. Execute the code
            result = self._execute_code(execution_context)

            # 3. Process outputs
            filtered_output = self._filter_outputs(result)

            del result,  execution_context

            # 4. Update state
            update_data =  VariableResolver.format_output(node_id=self.id, outputs=filtered_output)

            return Command(
                update=update_data,
                goto=self.next_node_ids
            )
        except Exception as e:
            error_msg = f"CodeNode execution failed [{self.title}]: {str(e)}"
            logger.error("code node error",error_msg=error_msg)
            traceback.print_exc()

            return self._handle_error(e)
        
    def _handle_error(self, e):
        if not self.error_strategy:
            raise e

        strategy_handlers = {
            "default-value": lambda: Command(
                update=VariableResolver.format_output(
                    node_id=self.id,
                    outputs={"text": self.default_value[0]['value'] if self.default_value else ''}
                ),
                goto=self.next_node_ids
            ),
            "fail-branch": lambda: Command(
                update={"node_id": self.id, "source_handle": "fail-branch"},
                goto=self.fail_branch_node_ids
            )
        }

        handler = strategy_handlers.get(self.error_strategy)
        if not handler:
            raise ValueError(f"Invalid error strategy: {self.error_strategy}")

        return handler()
    
    def _prepare_execution_context(self, state: GenericState) -> Dict[str, Any]:
        """Prepare the context variables for code execution."""
        context = {}

        # Extract values based on the node's configured variable mappings
        if self.variables:
            for var_config in self.variables:
                var_name = var_config.variable
                value_selector = var_config.value_selector
                value = VariableResolver.resolve_value_selector(value_selector, state)
                if isinstance(value, str):
                    context[var_name] = value.replace('```json', '').replace('```', '').strip()
                else:
                    context[var_name] = value

        logger.info(f"{self.formatted_name} code node context: {context}")
        return context
    
    def _execute_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the Python code."""
        if not self.code_language.lower().startswith("python"):
            raise ValueError(f"Unsupported code language: {self.code_language}")
            # Create a safe execution environment

        safe_globals = {
        '__builtins__': {
            # Basic types and type checks
            'len': len, 'sum': sum, 'max': max, 'min': min,
            'abs': abs, 'round': round, 'sorted': sorted,
            'range': range, 'enumerate': enumerate,'frozenset': frozenset,
            'zip': zip, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'isinstance': isinstance, 'type': type, 'hasattr': hasattr,

            # Encoding / decoding
            'bytes': bytes, 'bytearray': bytearray,

            # Exception classes
            'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
            'KeyError': KeyError, 'IndexError': IndexError, 'AttributeError': AttributeError,
            'NameError': NameError, 'ZeroDivisionError': ZeroDivisionError,
            'RuntimeError': RuntimeError, 'ImportError': ImportError,

            # Utility functions
            'print': print, 'repr': repr, 'hash': hash,
            'any': any, 'all': all, 'filter': filter, 'map': map,
            'iter': iter, 'next': next, 'open': open,

            # Module import
            '__import__': __import__,
            'object': object,
            'staticmethod': staticmethod,
            'classmethod': classmethod,
            'property': property,
            '__build_class__': __build_class__,
            '__name__' : '__main__',
        },
        "json": __import__("json")
    }
        # safe_globals['__build_class__'] = __build_class__
        # safe_globals['__name__'] = '__main__'
        # Execute the code
        local_vars = {}
        try:
            # Use globals as the execution namespace so imported modules are visible inside main()
            exec(self.code, safe_globals, safe_globals)
            local_vars = safe_globals
        except Exception as e:
            #print("{}_{}_{}_{} node run error: {}".format(self.wf_name, self.type, self.id, self.title, e))
            logger.error(f"{self.formatted_name} code node error",exc_info=True)
            raise RuntimeError(f"code run error: {e}, source code : {self.code}") 
        
        # Check that a main function is defined
        if 'main' not in local_vars:
            logger.error(f"{self.formatted_name} code node error",detail="Code must define a 'main' function")
            raise ValueError("Code must define a 'main' function")
        
        main_func = local_vars['main']
        if not callable(main_func):
            logger.error(f"{self.formatted_name} code node error",detail="'main' must be a callable function")
            raise ValueError("'main' must be a callable function")
        
        # Call the main function
        args = []
        try:
            # Inspect the main function's parameters
            import inspect
            sig = inspect.signature(main_func)
            params = list(sig.parameters.keys())

            # Prepare arguments
            for param in params:
                if param in context:
                    args.append(context[param])
                else:
                    logger.error(f"{self.formatted_name} code node error",detail=f"Missing required parameter: {param}")
                    raise ValueError(f"Missing required parameter: {param}")

            # Execute the main function
            result = main_func(*args)

            # Ensure the return value is a dict
            if not isinstance(result, dict):
                logger.error(f"{self.formatted_name} code node error",detail=f"main function must return a dict, got {type(result)}")
                raise ValueError(f"main function must return a dict, got {type(result)}")
            
            #print(f"[CodeNode] code execution result: {result}")
            return result
            
        except Exception as e:
            #print("{}_{}_{}_{} node run error: {}".format(self.wf_name, self.type, self.id, self.title, e))
            logger.error(f"{self.formatted_name} code node error",exc_info=True)
            raise RuntimeError(f"main func run error: {e}, source code : {self.code}, args : {args}") 
        
        finally:
            safe_globals.clear()
            args  = None
            
    
    def _filter_outputs(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """Filter results according to the output configuration."""
        if not self.outputs:
            # If no outputs are configured, return all results
            return execution_result

        # Only return the output variables specified in the configuration
        filtered = {}
        for var_name in self.outputs.keys():
            if var_name in execution_result:
                filtered[var_name] = execution_result[var_name]
            else:
                print(f"⚠️ Warning: expected output variable '{var_name}' not found in execution result")
        
        #print(f"[CodeNode] filtered output: {filtered}")
        return filtered