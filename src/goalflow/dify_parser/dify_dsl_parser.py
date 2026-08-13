import yaml
from typing import Optional,List,Dict
import ast
from goalflow.dify_parser.dify_app import (
    DifyDslDefinition, 
    DifyAppNode, 
    DifyDependenciesNode,
    DifyDependencyConfig, 
    DifyWorkflow
)

from goalflow.dify_parser.dify_types import (
    ConversationVar,
    DifyGraphNode,
    DifyLLMNodeData,
    MemoryConfig,
    DifyAnswerNodeData,
    LLMNodeModelConfig,
    DifyCodeNodeData,
    ContextConfig,
    DifyHttpRequestNodeData,
    DifyIfElseNodeData,
    Condition,
    DifyStartNodeData,
    NodeVarConfig,
    DifyQuestionClassifierNodeData,
    QuestionClassConfig,
    DifyVarAssignerNodeData,
    VariableOperationItem,
    DifyTemplateTransformerNodeData,
    DifyVariableAggregatorNodeData,
    AggregatorAdvancedSettings,
    DifyIterationNodeData,
    ErrorHandleMode,
    DifyIterationStartNodeData,
    DifyLoopStartNodeData,
    DifyLoopNodeData,
    DifyLoopEndNodeData,
    LoopVariableData,
    DifyGraphEdge,
    DifyEndNodeData,
    DifyToolNodeData,
    DifyKnowledgeNodeData,
    DifyAgentNodeData,
    DifyDocExtractorNodeData
)
from goalflow.constants import (
    WfNodeType,
    AssignerInputType,
    AssignerOperation,
    ErrorStrategy
)
from goalflow.workflow_types import (
    NodeVarConfig,
    SubCondition,
    SubVariableCondition,
    Condition,
    WfVariableConfig,
    VisionConfig,
    VisionConfigOptions,
    LLmNodePromptTemplate,
    PromptConfig,
    Case,
    HttpNodeAuthorizationConfig,
    HttpNodeApiKeyConfig,
    HttpRequestBodyConfig,
    HttpRequestBodyConfigItem,
    HttpNodeRetryConfig,
    HttpNodeTimeoutConfig,
    ToolInput,
    ToolParamSchema,
    EnvironmentVariable,
    DefaultValue,
)


class DifyDslParser:
    # Internal service address → substitution table for os.environ lookups at runtime.
    # Keys are hardcoded addresses that may appear in the exported DSL; values are the expressions used instead in the generated code.
    # In a code node the address is quoted (Python literal); in an http node the address is a bare string, so both forms are covered.
    DEFAULT_HOST_SUBSTITUTIONS: Dict[str, str] = {
        # code node (quoted string literal)
        "'http://39.44.47.98:8001/v1/rerank'": "os.environ['RERANK_URL']",
        "'http://39.11.230.55:8001/v1/rerank'": "os.environ['RERANK_URL']",
        # http node (bare address)
        "http://39.44.47.98:8001/v1/rerank": "'os.environ[\"RERANK_URL\"]'",
        "http://39.11.230.55:8001/v1/rerank": "'os.environ[\"RERANK_URL\"]'",
    }

    def __init__(
        self,
        dsl_path: str,
        host_substitutions: Optional[Dict[str, str]] = None,
    ):
        self.dsl_path = dsl_path
        # None → use the default table; passing an empty dict {} explicitly disables substitution.
        self.host_substitutions = (
            self.DEFAULT_HOST_SUBSTITUTIONS
            if host_substitutions is None
            else host_substitutions
        )

    def parse(self) -> DifyDslDefinition:
        # Read-only parsing: does not modify the user's exported file. Substitution only applies to the in-memory string.
        with open(self.dsl_path, "r", encoding="utf-8") as f:
            content = f.read()

        for old_text, new_text in self.host_substitutions.items():
            content = content.replace(old_text, new_text)

        data = yaml.load(content, yaml.CSafeLoader)
        return self.parse_data(data)

    def parse_data(self, data: dict) -> DifyDslDefinition:
        dsl_definition = DifyDslDefinition()
        
        app_node : DifyAppNode = self._parse_app(data["app"])
        dsl_definition.app = app_node
        
        dependencies_node : DifyDependenciesNode = self._parse_dependencies(data["dependencies"])
        dsl_definition.dependencies = dependencies_node
        
        workflow_node : DifyWorkflow = self._parse_workflow(data["workflow"])
        workflow_node.init_graph_data()
        
        dsl_definition.workflow = workflow_node
        
        return dsl_definition
    
    def _parse_app(self, app: dict) -> DifyAppNode:
        app_node = DifyAppNode()
        app_node.description = app["description"]
        app_node.icon = app["icon"]
        app_node.icon_background = app["icon_background"]
        app_node.mode = app["mode"]
        app_node.name = app["name"]
        app_node.use_icon_as_answer_icon = app["use_icon_as_answer_icon"]
        return app_node
    
    def _parse_dependencies(self, dependencies: list[dict]) -> DifyDependenciesNode:
        dependencies_node = DifyDependenciesNode()
        dependencies_node.dependencies = []
      
        for dependency in dependencies:
            dependency_config = DifyDependencyConfig()
            dependency_config.current_identifier = dependency["current_identifier"]
            dependency_config.type = dependency["type"]
            dependency_config.value = dependency["value"]
            dependencies_node.dependencies.append(dependency_config)
            
        return dependencies_node
    
    def _parse_workflow(self, workflow: dict) -> DifyWorkflow:
        workflow_node = DifyWorkflow()

        conversation_variables = self._parse_conversation_variables(workflow["conversation_variables"])
        workflow_node.conversation_variables = conversation_variables
        environment_variables = self._parse_environment_variables(workflow["environment_variables"])
        workflow_node.environment_variables = environment_variables
        #print(workflow_node.conversation_variables)
        #print(DifyWorkflow.conversation_variables)
        
        workflow_graph = workflow["graph"]
        workflow_node.nodes = []
       
        for node in workflow_graph["nodes"]:
            node_data = node["data"]
            node_type = node_data["type"]
            if node_type == '':
                print("ignore node:",node)
                continue
            workflow_node.add_node(self._parse_workflow_node(node))
         
        for edge in workflow_graph["edges"]:
            workflow_node.add_edge(self._parse_workflow_edge(edge))
        
        return workflow_node
    
    def _parse_conversation_variables(self, variables: list[dict]) -> List[NodeVarConfig]:
        conversation_variables = []
        for variable in variables:
            conversation_variables.append(ConversationVar(**variable))
            
        return conversation_variables
    
    def _parse_environment_variables(self, variables: list[dict]):
        environment_variables = []
        for variable in variables:
            environment_variables.append(EnvironmentVariable(**variable))
        return environment_variables

    
    def _parse_workflow_node(self, node: dict) -> DifyGraphNode:
        node_data = node["data"]
        node_type = WfNodeType.value_of(node_data["type"])
        print("parse node type:", node_type)
        common_node_fields = self._common_node_data_fields(node)
        data = None
        # Create the corresponding data object based on the node type
        if node_type == WfNodeType.LLM:
            context_config = ContextConfig()
            _context_config = node_data["context"]
            context_config.enabled = _context_config["enabled"]
            context_config.variable_selector = _context_config.get("variable_selector", None)
            
            memory_config = None
            if "memory" in node_data:
                memory_config = MemoryConfig()
                _memory_config = node_data["memory"]
                memory_config.query_prompt_template = _memory_config["query_prompt_template"]
                memory_config.role_prefix = _memory_config["role_prefix"]
                memory_config.window = _memory_config["window"]
            
            _prompt_template = node_data["prompt_template"]
            prompt_template = []
            for item in _prompt_template:
                prompt_template.append(LLmNodePromptTemplate(**item))
                
            prompt_config = None
            if "prompt_config" in node_data:
                _jinja2_variables = node_data["prompt_config"]
                jinja2_variables = []
                for item in _jinja2_variables:
                    jinja2_variables.append(NodeVarConfig(**item))
                
                prompt_config = PromptConfig(jinja2_variables=jinja2_variables)
            
            mode_config = LLMNodeModelConfig(**node_data["model"])
            
            vision_config = None
            _vision_config = node_data.get("vision", None)
            if _vision_config is not None:
                enabled = _vision_config["enabled"]
                options = None
                if "configs" in _vision_config:
                    variable_selector = _vision_config["configs"]["variable_selector"]
                    detail = _vision_config["configs"]["detail"]
                    
                    options = VisionConfigOptions()
                
                    if variable_selector is not None:
                        options.variable_selector = variable_selector
                    
                    if detail is not None:
                        options.detail = detail
                
                vision_config = VisionConfig(enabled=enabled, configs=options)
            
            data = DifyLLMNodeData(
                context=context_config,
                memory=memory_config,
                prompt_config=prompt_config,
                prompt_template=prompt_template,
                model=mode_config,
                vision=vision_config,
                **common_node_fields
            )
        elif node_type == WfNodeType.ANSWER:
            data = DifyAnswerNodeData(
                answer=node_data["answer"],
                **common_node_fields
            )
        elif node_type == WfNodeType.CODE:
            data = DifyCodeNodeData(
                code=node_data["code"],
                code_language=node_data["code_language"],
                outputs=node_data["outputs"],
                **common_node_fields
            )
            
            # Screen the code-node body at parse time; CodeNode re-validates at runtime.
            safe_check(data.code)
        elif node_type == WfNodeType.HTTP_REQUEST:
            # parse authorization
            _auth_config = node_data.get("authorization", None)
            if _auth_config is not None:
                auth_config_config = None
                auth_type = _auth_config["type"]
                
                _auth_config_config = _auth_config["config"]
                if _auth_config_config is not None:
                    auth_config_config = HttpNodeApiKeyConfig()
                    auth_config_config.api_key = _auth_config_config["api_key"]
                    if "header" in _auth_config_config:
                        auth_config_config.header = _auth_config_config["header"]
                    auth_config_config.type = _auth_config_config["type"]
                    
                auth_config = HttpNodeAuthorizationConfig(
                    config=auth_config_config,
                    type=auth_type
                )
            
            # parse body
            _body_config = node_data.get("body", None)
            body_config = HttpRequestBodyConfig()
            body_config.type = _body_config["type"]
            _body_config_data = _body_config["data"]
            body_config.data = []
            for item in _body_config_data:
                body_config.data.append(HttpRequestBodyConfigItem(**item))

            #parse retry_config
            _retry_config = node_data.get("retry_config", None)
            if _retry_config is not None:
                retry_config = HttpNodeRetryConfig(
                    max_retries=_retry_config["max_retries"],
                    retry_enabled=_retry_config["retry_enabled"],
                    retry_interval=_retry_config["retry_interval"]
                )
                
            #parse timeout_config
            _timeout_config = node_data.get("timeout_config", None)
            if _timeout_config is None:
                _timeout_config = node_data.get("timeout", None)
            timeout_config = None
            if _timeout_config is not None:
                timeout_config = HttpNodeTimeoutConfig(
                    max_connect_timeout=_timeout_config.get("max_connect_timeout",0) or _timeout_config.get("connect",0),
                    max_read_timeout=_timeout_config.get("max_read_timeout",0) or _timeout_config.get("read",0),
                    max_write_timeout=_timeout_config.get("max_write_timeout",0) or _timeout_config.get("write",0)
                )
            
            #parse headers
            headers_data = node_data.get("headers", '')
            headers = self._init_headers(headers_data)
            
            params_data = node_data.get("params", '')
            params = self._init_headers(params_data)
            
            data = DifyHttpRequestNodeData(
                url=node_data["url"],
                method=node_data["method"],
                ssl_verify=node_data.get("ssl_verify", True),
                authorization=auth_config,
                body=body_config,
                retry_config=retry_config,
                timeout_config=timeout_config,
                
                headers=headers,
                params=params,
                
                **common_node_fields
            )
        elif node_type == WfNodeType.IF_ELSE:
            # parse conditions
            conditions_node = node_data.get("conditions", None)
            conditions = self._new_condition_obj(conditions_node)

            # parse cases
            cases = []
            for item in node_data["cases"]:
                case = Case(
                    case_id=item["case_id"],
                    logical_operator=item["logical_operator"],
                    conditions=self._new_condition_obj(item.get("conditions", None))
                )

                cases.append(case)

            data = DifyIfElseNodeData(
                logical_operator=node_data.get("logical_operator", "and"),
                conditions=conditions,
                cases=cases,
                **common_node_fields
            )
        elif node_type == WfNodeType.START:
            variables = []
            for item in node_data["variables"]:
                variable_cofig = WfVariableConfig(**item)
                variables.append(variable_cofig)

            data = DifyStartNodeData(
                wf_inputs=variables,
                **common_node_fields    
            )
        elif node_type == WfNodeType.QUESTION_CLASSIFIER:
            question_class_configs = []

            _question_class = node_data["classes"]
            for item in _question_class:
                question_class_config = QuestionClassConfig(
                    id=item["id"],
                    name=item["name"]
                )
                
                question_class_configs.append(question_class_config)
                
            vision_config = None
            _vision_config = node_data.get("vision", None)
            if _vision_config is not None:
                enabled = _vision_config["enabled"]
                options = None
                if "configs" in _vision_config:
                    variable_selector = _vision_config["configs"]["variable_selector"]
                    detail = _vision_config["configs"]["detail"]
                    
                    options = VisionConfigOptions()
                
                    if variable_selector is not None:
                        options.variable_selector = variable_selector
                    
                    if detail is not None:
                        options.detail = detail
                
                vision_config = VisionConfig(enabled=enabled, configs=options)

            
            _memory_config = node_data["memory"] if "memory" in node_data else None
            if _memory_config is not None:
                memory_config = MemoryConfig()
                memory_config.query_prompt_template = _memory_config["query_prompt_template"]
                memory_config.role_prefix = _memory_config.get("role_prefix", None)
                memory_config.window = _memory_config["window"]

            data = DifyQuestionClassifierNodeData(
                classes=question_class_configs,
                instruction=node_data["instruction"] if "instruction" in node_data else None,
                query_variable_selector=node_data["query_variable_selector"],
                
                model=LLMNodeModelConfig(**node_data["model"]),
                memory= memory_config if _memory_config is not None else None,
                vision=vision_config,
                
                **common_node_fields
            )
        elif node_type == WfNodeType.ASSIGNER:
            _items_node = node_data["items"]
            items = []
            for _item_node in _items_node:
                input_type = AssignerInputType.value_of(_item_node["input_type"])
                operation = AssignerOperation.value_of(_item_node["operation"])
                variable_selector = _item_node["variable_selector"]
                value = _item_node["value"]
                
                # For the three operations below, the value source can only be a variable
                if any([
                    operation == AssignerOperation.OVER_WRITE,
                    operation == AssignerOperation.APPEND,
                    operation == AssignerOperation.EXTEND,
                ]):
                    if value is None:
                        raise ValueError("assigner_node : value is None")
                    if value != "" and type(value) != list:
                        raise ValueError("assigner_node: value must be list as var_selector")

                var_operation_item = VariableOperationItem()
                var_operation_item.input_type = input_type
                var_operation_item.operation = operation
                var_operation_item.variable_selector = variable_selector
                var_operation_item.value = value
                
                items.append(var_operation_item)

            data = DifyVarAssignerNodeData(
                items=items,
                **common_node_fields
            )
        elif node_type == WfNodeType.TEMPLATE_TRANSFORM:
            template=node_data["template"]
            data = DifyTemplateTransformerNodeData(
                template=template,
                **common_node_fields
            )
        elif node_type == WfNodeType.VARIABLE_AGGREGATOR:
            advanced_settings_node = node_data.get("advanced_settings", None)
            advanced_settings = None
            if advanced_settings_node is not None:
                advanced_settings = AggregatorAdvancedSettings()
                advanced_settings.groups = []
                advanced_settings.group_enabled = advanced_settings_node["group_enabled"]
                for group_node in advanced_settings_node["groups"]:
                    group = AggregatorAdvancedSettings.Group()
                    group.output_type = group_node["output_type"]
                    group.variables = group_node["variables"]
                    group.group_name = group_node["group_name"]
                    advanced_settings.groups.append(group)
            
            data = DifyVariableAggregatorNodeData(
                output_type=node_data["output_type"],
                variable_selectors=node_data["variables"],
                advanced_settings=advanced_settings,
                
                **common_node_fields
            )
        elif node_type == WfNodeType.ITERATION:
            parallel_nums = node_data.get("parallel_nums", 4)
            error_handle_mode = ErrorHandleMode.value_of(node_data["error_handle_mode"])

            data = DifyIterationNodeData(
                start_node_id=node_data["start_node_id"],
                parallel_nums=parallel_nums,
                error_handle_mode=error_handle_mode,
                #This only parses; the langgraph implementation forces parallelism internally, even if this is set to False
                is_parallel=node_data.get("is_parallel", True),
                iterator_selector=node_data["iterator_selector"],
                output_selector=node_data["output_selector"],
                output_type=node_data["output_type"],
                
                **common_node_fields
            )
        elif node_type == WfNodeType.ITERATION_START:
            data = DifyIterationStartNodeData(
                **common_node_fields
            )
        elif node_type == WfNodeType.LOOP_START:
            data = DifyLoopStartNodeData(
                **common_node_fields
            )
        elif node_type == WfNodeType.LOOP_END:
            data = DifyLoopEndNodeData(
                **common_node_fields
            )
        elif node_type == WfNodeType.LOOP:
            start_node_id = node_data["start_node_id"]
            _error_handle_mode = node_data.get("error_handle_mode", None)
            error_handle_mode = (
                ErrorHandleMode.value_of(_error_handle_mode)
                if _error_handle_mode is not None
                else ErrorHandleMode.TERMINATED
            )
            loop_count = node_data["loop_count"]
            logical_operator = node_data["logical_operator"]
            outputs = node_data.get("outputs", None) 
            
            _break_conditions = node_data.get("break_conditions", None)
            break_conditions = self._new_condition_obj(_break_conditions)
            
            _loop_variables = node_data.get("loop_variables", None)
            loop_variables = (
                [] if _loop_variables is None
                else [LoopVariableData(**item) for item in _loop_variables]
            )
        
            data = DifyLoopNodeData(
                start_node_id=start_node_id,
                error_handle_mode=error_handle_mode,
                loop_count=loop_count,
                logical_operator=logical_operator,
                outputs=outputs,
                break_conditions=break_conditions,
                loop_variables=loop_variables,

                **common_node_fields
            )
        # removed later
        elif node_type == WfNodeType.KNOWLEDGE_RETRIEVAL:
            data = DifyKnowledgeNodeData(
                **common_node_fields
            )
        elif node_type == WfNodeType.TOOL:
            tool_parameters_data = node_data.get("tool_parameters", None)
            param_schemas_data = node_data.get("paramSchemas", None)
            tool_parameters = None
            if tool_parameters_data:
                tool_parameters = {k: ToolInput(**v) for k, v in tool_parameters_data.items()}
            param_schemas = None
            if param_schemas_data:
                param_schemas = [ToolParamSchema(**item) for item in param_schemas_data]

            data = DifyToolNodeData(
                provider_id=node_data.get("provider_id", None),
                provider_name=node_data.get("provider_name", None),
                provider_type=node_data.get("provider_type", None),
                tool_name=node_data.get("tool_name", None),
                tool_label=node_data.get("tool_label", None),
                tool_configurations=node_data.get("tool_configurations", None),
                tool_parameters=tool_parameters,
                param_schemas=param_schemas,
                **common_node_fields
            )
        elif node_type == WfNodeType.END:
            outputs = node_data["outputs"]
            outputs = [NodeVarConfig(**item) for item in outputs]
            data = DifyEndNodeData(
                outputs=outputs,
                **common_node_fields
            )
        elif node_type == WfNodeType.AGENT:
            
            data = DifyAgentNodeData(
                agent_parameters=node_data.get("agent_parameters",None),
                agent_strategy_label=node_data.get("agent_strategy_label",None),
                agent_strategy_name=node_data.get("agent_strategy_name",None),
                agent_strategy_provider_name=node_data.get("agent_strategy_provider_name",None),
                output_schema=node_data.get("output_schema",None),
                plugin_unique_identifier=node_data.get("plugin_unique_identifier",None),
                **common_node_fields
            )
        elif node_type == WfNodeType.DOCUMENT_EXTRACTOR:
            data = DifyDocExtractorNodeData(
                is_array_file=node_data.get("is_array_file",False),
                variable_selector=node_data.get("variable_selector",None),
                **common_node_fields
            )
        else:
            raise Exception(f"parse error, invalid node type: {node_type} !")

        
        # Create and return the DifyNode instance
        return DifyGraphNode(
            data=data,
            id=node["id"],
            height=node["height"],
            width=node["width"],
            position=node["position"],
            positionAbsolute=node["positionAbsolute"],
            selected=node.get("selected", False),
            sourcePosition=node["sourcePosition"],
            targetPosition=node["targetPosition"],
            type=node["type"],
            parentId=node.get("parentId", None),
        )
        
    def _parse_workflow_edge(self, edge: dict) -> DifyGraphEdge:
        return DifyGraphEdge(
            id=edge["id"],
            source=edge["source"],
            sourceHandle=edge["sourceHandle"],
            target=edge["target"],
            targetHandle=edge["targetHandle"],
            sourceType=edge.get("sourceType", None),
            targetType=edge.get("targetType", None),
            isInIteration=edge.get("isInIteration", False),
            isInLoop=edge.get("isInLoop", False),
            selected=edge.get("selected", False),
            type=edge["type"]
        )
    
    def _init_headers(self, headers: str) -> Optional[dict]:
        """
        Convert the header string of frontend to a dictionary.

        Each line in the header string represents a key-value pair.
        Keys and values are separated by ':'.
        Empty values are allowed.

        Examples:
            'aa:bb\n cc:dd'  -> {'aa': 'bb', 'cc': 'dd'}
            'aa:\n cc:dd\n'  -> {'aa': '', 'cc': 'dd'}
            'aa\n cc : dd'   -> {'aa': '', 'cc': 'dd'}

        """
        if not headers:
            return None
        #headers = self.variable_pool.convert_template(self.node_data.headers).text
        return {
            key.strip(): (value[0].strip() if value else "")
            for line in headers.splitlines()
            if line.strip()
            for key, *value in [line.split(":", 1)]
        }
    
    def _common_node_data_fields(self, node: dict) -> dict:
        """
        Initialize the common fields of the node data.

        Args:
            node_data (dict): the raw dictionary of node data.

        Returns:
            dict: a dictionary containing the common fields.
        """
        node_data = node["data"]
        node_type = node_data["type"]

        variables = (
            None if any([node_type == WfNodeType.START.value ,
                        node_type == WfNodeType.VARIABLE_AGGREGATOR.value])
            else self._initVarConfig(node_data.get("variables", None)) 
        )

        ret =  {
            "desc": node_data.get("desc", ""),
            "selected": node_data["selected"],
            "title": node_data["title"],
            "type": node_data["type"],
            #"variables": variables,
            "isInIteration": node_data.get("isInIteration", False),
            "isInLoop": node_data.get("isInLoop", False),
            "iteration_id": node_data.get("iteration_id", None),
            "loop_id": node_data.get("loop_id", None),
            "parentId": node_data.get("parentId", None)
        }
        
        if variables is not None:
            ret["variables"] = variables
            
        error_strategy = node_data.get("error_strategy", None)
        if error_strategy is not None:
            ret["error_strategy"] = error_strategy
            
        default_value = node_data.get("default_value", None)  
        if default_value is not None:
            ret["default_value"] = default_value
        
        return ret
        
    def _initVarConfig(self,variables : List[Dict[str,object]]) ->Optional[List[NodeVarConfig]] :

        if variables is None:
            return None
        
        input_vars_config = []
                
        for var in variables:
            input_vars_config.append(NodeVarConfig(**var))
            
        return input_vars_config

        
    def _new_condition_obj(self, conditions_node:Optional[dict]) -> list|None:
        if conditions_node is None:
            return None
        
        conditions = []
        for item in conditions_node:
            condition = Condition(
                varType=item["varType"],
                comparison_operator=item["comparison_operator"],
                value=item["value"],
                variable_selector=item["variable_selector"],
            )

            conditions.append(condition)
            
            _sub_cond_node = item.get("sub_variable_condition", None)
            
            print(_sub_cond_node)
            if _sub_cond_node is not None:
                _sub_conds = _sub_cond_node.get("conditions", [])
                
                
                sub_conditions = []
                for sub_item in _sub_conds:
                    sub_condition = SubCondition()
                    sub_condition.comparison_operator = sub_item["comparison_operator"]
                    sub_condition.value = sub_item["value"]
                    sub_condition.key = sub_item["key"]
                    sub_conditions.append(sub_condition)
                    
                #sub_variable_condition.conditions = sub_conditions
                #sub_variable_condition.logical_operator = _sub_cond_node["logical_operator"]
                
                sub_variable_condition = SubVariableCondition(
                    logical_operator=_sub_cond_node["logical_operator"],
                    conditions=sub_conditions
                )
                
                condition.sub_variable_condition = sub_variable_condition
            
        return conditions

# simple safe check
# Names and attributes that indicate a code node is attempting host/process access
# or a sandbox escape. This is a coarse screen at parse time; the CodeNode runtime
# performs the authoritative AST validation before execution.
_UNSAFE_CALL_NAMES = frozenset({
    "open", "eval", "exec", "compile", "__import__",
    "globals", "vars", "getattr", "setattr", "delattr", "input",
})

# Modules a code node may import. Kept in sync with CodeNode.ALLOWED_IMPORT_MODULES;
# anything giving process/filesystem/network access is excluded.
_ALLOWED_IMPORT_MODULES = frozenset({
    "json", "math", "re", "datetime", "random", "statistics",
    "decimal", "fractions", "collections", "itertools", "functools",
    "string", "base64", "hashlib", "uuid", "time",
})


def safe_check(code: str):
    if code is None:
        return

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"code node syntax error: {e}") from e

    for node in ast.walk(tree):
        # Reject calls to dangerous builtins, e.g. open(...) / eval(...).
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _UNSAFE_CALL_NAMES
        ):
            raise ValueError(
                f"unsafe function call '{node.func.id}' not allowed in code node"
            )
        # Reject dunder attribute access used for ().__class__.__subclasses__() escapes.
        if (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr.endswith("__")
        ):
            raise ValueError(
                f"access to dunder attribute '{node.attr}' not allowed in code node"
            )
        # Reject imports of modules outside the compute-only allowlist.
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".", 1)[0]
                if top_level not in _ALLOWED_IMPORT_MODULES:
                    raise ValueError(
                        f"import of module '{alias.name}' not allowed in code node"
                    )
        if isinstance(node, ast.ImportFrom):
            top_level = (node.module or "").split(".", 1)[0]
            if top_level not in _ALLOWED_IMPORT_MODULES:
                raise ValueError(
                    f"import from module '{node.module}' not allowed in code node"
                )