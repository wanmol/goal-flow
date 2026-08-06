from goalflow.dify_parser import (
    DifyWorkflow,
    DifyDslParser,
    DifyDslDefinition,
    DifyAppNode,
    DIFY_APP_MODE_WORKFLOW,
    DIFY_APP_MODE_ADVANCED_CHATFLOW
)
from goalflow.visitor.node_visitor import DifyNodeVisitor
from goalflow.constants import WfNodeType,WF_TYPE_WORKFLOW,WF_TYPE_CHATFLOW
from typing import Optional
from goalflow.workflow_types import EnvironmentVariable,ConversationVar
import os


class WorkflowCodeGenerator:
    """
    Transforms Dify workflow definitions into executable workflow code.
    """
    
    def __init__(
        self,
        dsl_path: str,
        *,
        file_name : str = "workflow.py",
        class_name: Optional[str] = None,
        out_path: Optional[str] = None,
    ):
        if dsl_path is None:
            raise ValueError("dsl_path is None")

        self.dsl_parser = DifyDslParser(dsl_path)
        self.visitor = DifyNodeVisitor()
        self.generated_code = ""
        self.file_name = file_name
        self.class_name = class_name
        # out_path: 显式输出路径（文件或目录）。None → 默认写入 workflow/generated/<file_name>。
        self.out_path = out_path
        
    def generate(self):
        
        definition: DifyDslDefinition = self.dsl_parser.parse()
        dify_wf : DifyWorkflow = definition.workflow
        app:DifyAppNode = definition.app

        self.visitor.workflow = dify_wf
        
        code : str = self.do_generate(dify_wf,app)

        filename = self._resolve_output_path()
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)
        return filename

    def _resolve_output_path(self) -> str:
        """决定生成文件的落地路径。

        - out_path 为 None：默认写入 workflow/generated/<file_name>
        - out_path 是已存在的目录（或以分隔符结尾）：视为目录，文件名用 file_name
        - out_path 否则视为完整文件路径
        """
        if self.out_path is None:
            generated_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "workflow",
                "generated",
            )
            return os.path.join(generated_dir, self.file_name)

        out = os.path.abspath(self.out_path)
        if os.path.isdir(out) or self.out_path.endswith(("/", os.sep)):
            return os.path.join(out, self.file_name)
        return out
    
    def do_generate(self, workflow: DifyWorkflow,app:DifyAppNode) -> str:
        """
        Transform a Dify workflow into executable Python code.
        
        Args:
            workflow: The DifyWorkflow object to transform
            
        Returns:
            Generated Python code as a string
        """
        app_mode = app.mode
        wf_type = None
        if app_mode == DIFY_APP_MODE_WORKFLOW:
            wf_type = WF_TYPE_WORKFLOW
        elif app_mode == DIFY_APP_MODE_ADVANCED_CHATFLOW:
            wf_type = WF_TYPE_CHATFLOW
        else:
            raise ValueError(f"Unknown app mode: {app_mode}")
        
        self.generated_code = ""
        
        # Generate basic workflow structure
        self._generate_imports()
        self._generate_workflow_class(workflow,wf_type)
        
        return self.generated_code
    
    def _generate_imports(self):
        """Generate necessary import statements"""
        imports = [
            "from typing import Dict, Any",
            "from goalflow.state import GenericState,BaseState",
            "from langgraph.graph import StateGraph,START",
            "from goalflow.node import *",
            "from goalflow.dify_parser.dify_types import *",
            "from goalflow.workflow_types import *",
            "from goalflow.constants import *",
            "from typing import Iterator,Any",
            "from goalflow.workflow.base_workflow import BaseWorkflow,GraphEdge",
            "import os"
        ]
        
        self.generated_code += "\n".join(imports) + "\n\n"
    
    def _generate_workflow_class(self, workflow: DifyWorkflow,wf_type:str):
        """Generate the workflow class"""
        
        class_name_prefix = self.class_name
        if class_name_prefix is None:
            class_name_prefix = f"GeneratedWorkflow_{workflow.start_node_id}"
        
        class_name = f"{class_name_prefix}(BaseWorkflow[BaseState])"

        for node in workflow.nodes:
            self.visitor.visit(node)
            
        for edge in workflow.edges:
            self.visitor.visit_edge(edge)
            
        node_code = self.visitor.get_node_code()
        edge_code = self.visitor.get_edge_code()

        class_code = f'''class {class_name}:
    """Generated workflow for: {workflow.start_node_id}"""
    
    def __init__(self,config_schema:str=None,workflow_type:str="{wf_type}"):
        super().__init__(config_schema, workflow_type)
    
    def _setup_environment_variables(self):
        "auto bind all environment variables"
        {self._bind_environment_variables(workflow)}
        
    def _setup_conversation_variables(self):
        "auto bind all conversation variables"
        {self._bind_conversation_variables(workflow)}
    
    def _setup_nodes(self):
        """Setup all workflow nodes"""
        {node_code}
        
    def _setup_edges(self):
        """Setup all workflow edges"""
        {edge_code}
    
    #def execute(self, initial_state: GenericState) -> GenericState:
    #    """Execute the workflow"""
    #    return self.compiled_graph.invoke(initial_state)
    
    #def stream(self, initial_state: GenericState,
    #    stream_mode : List[str] = ["messages","updates"]
    #) -> Iterator[Any]:
    #    """Execute the workflow"""
    #    yield from self.compiled_graph.stream(initial_state,stream_mode=stream_mode)
    
    def _fix_common_args(self, common_args: dict):
        if "variables" in common_args and common_args["variables"]:
            common_args["variables"] = [NodeVarConfig.from_json(var) for var in common_args["variables"]] 
                
        if "error_strategy" in common_args and common_args["error_strategy"]:
            common_args["error_strategy"] = ErrorStrategy.value_of(common_args["error_strategy"])
        
        if "default_value" in common_args and common_args["default_value"]:
            common_args["default_value"] = [DefaultValue.from_json(dv) for dv in common_args["default_value"]] 

        return common_args
'''
        self.generated_code += class_code
        
    def _bind_conversation_variables(self,dify_wf:DifyWorkflow):
        conversation_variables:list[ConversationVar] = dify_wf.conversation_variables
        conv_list:list = [item.to_json() for item in conversation_variables ]
        
        code = f'''
        conversation_list = []
        for conv in {conv_list}:
            conversation_list.append(ConversationVar.from_json(conv))
        self.conversation_list = conversation_list
        '''
        return code
        
    def _bind_environment_variables(self,dify_wf:DifyWorkflow):
        environment_variables:list[EnvironmentVariable] = dify_wf.environment_variables
        env_list:list = [item.to_json() for item in environment_variables ]
        
        code = f'''
        environment_list = []
        for env in {env_list}:
            environment_list.append(EnvironmentVariable.from_json(env))
        self.environment_list = environment_list
        '''
        return code
        