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
    
    # 需要改造成可以直接传外部函数（支持手工流程编排）
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
        动态执行Python代码，支持从state中获取变量并返回结果
        """

        #print(state)
        
        logger.info(f"{self.formatted_name} code node process",code=self.code)
        #print(repr(self.code))
        #self.code = repr(self.code)

        import traceback

        try:
            # 1. 准备执行环境和变量
            execution_context = self._prepare_execution_context(state)
            
            # 2. 执行代码
            result = self._execute_code(execution_context)
            
            # 3. 处理输出
            filtered_output = self._filter_outputs(result)
            
            del result,  execution_context
            
            # 4. 更新状态
            update_data =  VariableResolver.format_output(node_id=self.id, outputs=filtered_output)

            return Command(
                update=update_data,
                goto=self.next_node_ids
            )
        except Exception as e:
            error_msg = f"CodeNode执行失败 [{self.title}]: {str(e)}"
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
        """准备代码执行的上下文变量"""
        context = {}

        # 根据节点配置的变量映射提取值
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
        """执行Python代码"""
        if not self.code_language.lower().startswith("python"):
            raise ValueError(f"不支持的代码语言: {self.code_language}")
            # 创建安全的执行环境

        safe_globals = {
        '__builtins__': {
            # 基本类型和类型检查
            'len': len, 'sum': sum, 'max': max, 'min': min,
            'abs': abs, 'round': round, 'sorted': sorted,
            'range': range, 'enumerate': enumerate,'frozenset': frozenset,
            'zip': zip, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'isinstance': isinstance, 'type': type, 'hasattr': hasattr,

            # 加解密
            'bytes': bytes, 'bytearray': bytearray,
            
            # 异常类
            'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
            'KeyError': KeyError, 'IndexError': IndexError, 'AttributeError': AttributeError,
            'NameError': NameError, 'ZeroDivisionError': ZeroDivisionError,
            'RuntimeError': RuntimeError, 'ImportError': ImportError,

            # 实用函数
            'print': print, 'repr': repr, 'hash': hash,
            'any': any, 'all': all, 'filter': filter, 'map': map,
            'iter': iter, 'next': next, 'open': open,
                 
            # 模块导入
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
        # 执行代码
        local_vars = {}
        try:
            # 使用globals作为执行环境，这样import的模块可以在main函数中访问
            exec(self.code, safe_globals, safe_globals)
            local_vars = safe_globals
        except Exception as e:
            #print("{}_{}_{}_{} node run error: {}".format(self.wf_name, self.type, self.id, self.title, e))
            logger.error(f"{self.formatted_name} code node error",exc_info=True)
            raise RuntimeError(f"code run error: {e}, source code : {self.code}") 
        
        # 检查是否定义了main函数
        if 'main' not in local_vars:
            logger.error(f"{self.formatted_name} code node error",detail="Code must define a 'main' function")
            raise ValueError("Code must define a 'main' function")
        
        main_func = local_vars['main']
        if not callable(main_func):
            logger.error(f"{self.formatted_name} code node error",detail="'main' must be a callable function")
            raise ValueError("'main' must be a callable function")
        
        # 调用main函数
        args = []
        try:
            # 获取main函数的参数
            import inspect
            sig = inspect.signature(main_func)
            params = list(sig.parameters.keys())
            
            # 准备参数
            for param in params:
                if param in context:
                    args.append(context[param])
                else:
                    logger.error(f"{self.formatted_name} code node error",detail=f"Missing required parameter: {param}")
                    raise ValueError(f"Missing required parameter: {param}")

            # 执行main函数
            result = main_func(*args)
            
            # 确保返回值是字典
            if not isinstance(result, dict):
                logger.error(f"{self.formatted_name} code node error",detail=f"main function must return a dict, got {type(result)}")
                raise ValueError(f"main function must return a dict, got {type(result)}")
            
            #print(f"[CodeNode] 代码执行结果: {result}")
            return result
            
        except Exception as e:
            #print("{}_{}_{}_{} node run error: {}".format(self.wf_name, self.type, self.id, self.title, e))
            logger.error(f"{self.formatted_name} code node error",exc_info=True)
            raise RuntimeError(f"main func run error: {e}, source code : {self.code}, args : {args}") 
        
        finally:
            safe_globals.clear()
            args  = None
            
    
    def _filter_outputs(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """根据输出配置过滤结果"""
        if not self.outputs:
            # 如果没有配置输出，返回所有结果
            return execution_result
        
        # 只返回配置中指定的输出变量
        filtered = {}
        for var_name in self.outputs.keys():
            if var_name in execution_result:
                filtered[var_name] = execution_result[var_name]
            else:
                print(f"⚠️ 警告: 期望的输出变量 '{var_name}' 不存在于执行结果中")
        
        #print(f"[CodeNode] 过滤后输出: {filtered}")
        return filtered