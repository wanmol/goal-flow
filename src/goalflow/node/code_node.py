from goalflow.node.base import BaseNode,NodeOutput
from typing import Dict, Any, Optional
from pydantic import BaseModel
from goalflow.state import GenericState
from goalflow.constants import WfNodeType
from goalflow.tool.utils import VariableResolver
from langgraph.graph.state import Command

from goalflow.config import get_logger

logger = get_logger(__name__)

# Modules a code node is allowed to import. Anything giving process/filesystem/
# network access (os, sys, subprocess, socket, importlib, ctypes, ...) is excluded
# on purpose. Keep this list narrow; add only side-effect-free compute modules.
ALLOWED_IMPORT_MODULES = frozenset({
    "json", "math", "re", "datetime", "random", "statistics",
    "decimal", "fractions", "collections", "itertools", "functools",
    "string", "base64", "hashlib", "uuid", "time",
})

# Builtin names that are never allowed to be referenced from user code. These are
# the primitives used to escape the restricted namespace or reach the host.
BLOCKED_BUILTIN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "__import__", "globals", "vars",
    "getattr", "setattr", "delattr", "input", "breakpoint", "memoryview",
    "__builtins__", "object",
})


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """A restricted replacement for __import__ that only permits an allowlist.

    The import machinery (the ``import`` statement) calls this, so it guards both
    explicit and statement-form imports as defense-in-depth alongside the AST scan.
    """
    top_level = name.split(".", 1)[0]
    if top_level not in ALLOWED_IMPORT_MODULES:
        raise ImportError(f"import of module '{name}' is not allowed in code node")
    return __import__(name, globals, locals, fromlist, level)


def _validate_code_ast(code: str) -> None:
    """Statically reject code that could escape the restricted exec namespace.

    Blocks dunder attribute access (``__class__``/``__subclasses__``/``__globals__``
    ... — the standard sandbox-escape traversal), references to dangerous builtin
    names, and imports of modules outside the allowlist. This is a screen, not a
    substitute for a real OS-level sandbox, but it removes the trivial escapes.
    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"code node syntax error: {e}") from e

    for node in ast.walk(tree):
        # Dunder attribute access is the pivot for ().__class__.__subclasses__()
        # style escapes; disallow any __dunder__ attribute.
        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                raise ValueError(
                    f"access to dunder attribute '{attr}' is not allowed in code node"
                )
        # Direct references to dangerous builtins.
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_BUILTIN_NAMES:
                raise ValueError(
                    f"use of '{node.id}' is not allowed in code node"
                )
        # import os / import subprocess as x / from os import ...
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".", 1)[0]
                if top_level not in ALLOWED_IMPORT_MODULES:
                    raise ValueError(
                        f"import of module '{alias.name}' is not allowed in code node"
                    )
        elif isinstance(node, ast.ImportFrom):
            top_level = (node.module or "").split(".", 1)[0]
            if top_level not in ALLOWED_IMPORT_MODULES:
                raise ValueError(
                    f"import from module '{node.module}' is not allowed in code node"
                )


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

        # Statically screen the source before executing it: reject dunder-attribute
        # escapes, dangerous builtin names, and non-allowlisted imports.
        _validate_code_ast(self.code)

        # Create a restricted execution environment. Note: exec() on untrusted input
        # is not a true security boundary (no CPU/memory/time limits); the AST scan
        # plus this trimmed builtin set only removes the trivial escape paths. For
        # hostile input, run this in an OS-level sandbox (subprocess + seccomp/nsjail).
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
            'iter': iter, 'next': next,

            # Restricted import: only the compute-only allowlist above. Needed so
            # both `import json` statements and internal machinery work, but nothing
            # that reaches the OS/network can be imported.
            '__import__': _safe_import,
            'staticmethod': staticmethod,
            'classmethod': classmethod,
            'property': property,
            # __build_class__ is required so `class` statements work inside user code.
            '__build_class__': __build_class__,
            '__name__' : '__main__',
        },
        "json": __import__("json")
    }
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