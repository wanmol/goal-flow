from abc import ABC, abstractmethod
from typing import Optional,List
from goalflow.dify_parser.dify_types import (
    DifyGraphNode, 
    DifyStartNodeData, 
    DifyQuestionClassifierNodeData,
    DifyLLMNodeData, 
    DifyCodeNodeData, 
    DifyHttpRequestNodeData,
    DifyIfElseNodeData, 
    DifyIterationNodeData, 
    DifyLoopNodeData,
    DifyLoopEndNodeData,
    DifyNodeDataBase,
    DifyAnswerNodeData,
    DifyIterationStartNodeData,
    DifyLoopStartNodeData,
    DifyEndNodeData,
    DifyToolNodeData,
    DifyKnowledgeNodeData,
    DifyAgentNodeData,
    DifyVarAssignerNodeData,
    DifyTemplateTransformerNodeData,
    DifyVariableAggregatorNodeData,
    DifyDocExtractorNodeData
)
from goalflow.constants import WfNodeType
from goalflow.workflow_types import (
    LLMNodeModelConfig, 
    MemoryConfig,
    QuestionClassConfig,
    ContextConfig,
    LLmNodePromptTemplate,
    VisionConfig,
    VisionConfigOptions,
    Case,
    Condition,
    HttpRequestBodyConfig,
    HttpNodeAuthorizationConfig,
    HttpNodeRetryConfig,
    HttpNodeTimeoutConfig,
    ToolInput,
    ToolParamSchema,
    LoopVariableData,
    AgentToolParameterConfig,
    VariableOperationItem,
    AggregatorAdvancedSettings,
    WfVariableConfig
)

from goalflow.dify_parser.dify_app import DifyWorkflow,DifyGraphEdge
from collections import defaultdict
import json


class DifyNodeAbstractVisitor(ABC):
    """Abstract visitor for processing Dify workflow nodes."""
    
    def visit(self, node: DifyGraphNode):
        """Dispatch the visit to the appropriate method based on the node type."""
        # temp 
        if node.data is None:
            return
        
        node_type = WfNodeType.value_of(node.data.type)

        if node_type == WfNodeType.START:
            self.visit_start(node)
        elif node_type == WfNodeType.QUESTION_CLASSIFIER:
            self.visit_classifier(node)
        elif node_type == WfNodeType.LLM:
            self.visit_llm(node)
        elif node_type == WfNodeType.CODE:
            self.visit_code(node)
        elif node_type == WfNodeType.HTTP_REQUEST:
            self.visit_http_request(node)
        elif node_type == WfNodeType.IF_ELSE:
            self.visit_if_else(node)
        elif node_type == WfNodeType.ITERATION:
            self.visit_iteration(node)
        elif node_type == WfNodeType.ITERATION_START:
            self.visit_iteration_start(node)    
        elif node_type == WfNodeType.LOOP:
            self.visit_loop(node)
        elif node_type == WfNodeType.LOOP_START:
            self.visit_loop_start(node)
        elif node_type == WfNodeType.LOOP_END:
            self.visit_loop_end(node)
        elif node_type == WfNodeType.TOOL:
            self.visit_tool(node)
        elif node_type == WfNodeType.ANSWER:
            self.visit_answer(node)
        elif node_type == WfNodeType.END:
            self.visit_end(node)
        elif node_type == WfNodeType.KNOWLEDGE_RETRIEVAL:
            self.visit_knowledge_retrieval(node)
        elif node_type == WfNodeType.ASSIGNER:
            self.visit_assigner(node)
        elif node_type == WfNodeType.AGENT:
            self.visit_agent(node)
        elif node_type == WfNodeType.TEMPLATE_TRANSFORM:
            self.visit_template_transform(node)
        elif node_type == WfNodeType.VARIABLE_AGGREGATOR:
            self.visit_variable_aggregator(node)
        elif node_type == WfNodeType.DOCUMENT_EXTRACTOR:
            self.visit_doc_extractor(node)
        else:
            self.visit_generic(node)

    
    @abstractmethod
    def visit_start(self, node: DifyGraphNode[DifyStartNodeData]):
        pass
    
    @abstractmethod
    def visit_classifier(self, node: DifyGraphNode[DifyQuestionClassifierNodeData]):
        pass
    
    @abstractmethod
    def visit_llm(self, node: DifyGraphNode[DifyLLMNodeData]):
        pass
    
    @abstractmethod
    def visit_code(self, node: DifyGraphNode[DifyCodeNodeData]):
        pass
    
    @abstractmethod
    def visit_http_request(self, node: DifyGraphNode[DifyHttpRequestNodeData]):
        pass
    
    @abstractmethod
    def visit_if_else(self, node: DifyGraphNode[DifyIfElseNodeData]):
        pass
    
    @abstractmethod
    def visit_iteration(self, node: DifyGraphNode[DifyIterationNodeData]):
        pass
    
    @abstractmethod
    def visit_iteration_start(self, node: DifyGraphNode[DifyIterationStartNodeData]):
        pass

    
    @abstractmethod
    def visit_loop(self, node: DifyGraphNode[DifyLoopNodeData]):
        pass
    
    @abstractmethod
    def visit_loop_start(self, node: DifyGraphNode[DifyLoopStartNodeData]):
        pass
    
    @abstractmethod
    def visit_loop_end(self, node: DifyGraphNode[DifyLoopEndNodeData]):
        pass

    
    @abstractmethod
    def visit_tool(self, node: DifyGraphNode):
        pass
    
    @abstractmethod
    def visit_answer(self, node: DifyGraphNode[DifyAnswerNodeData]):
        pass
    
    @abstractmethod
    def visit_answer(self, node: DifyGraphNode[DifyAnswerNodeData]):
        pass
    
    @abstractmethod
    def visit_end(self, node: DifyGraphNode[DifyEndNodeData]):
        pass
    
    @abstractmethod
    def visit_knowledge_retrieval(self, node: DifyGraphNode[DifyKnowledgeNodeData]):
        pass
    
    @abstractmethod
    def visit_agent(self, node: DifyGraphNode[DifyAgentNodeData]):
        pass
    
    @abstractmethod
    def visit_assigner(self, node: DifyGraphNode[DifyVarAssignerNodeData]):
        pass
    
    @abstractmethod
    def visit_template_transform(self, node: DifyGraphNode[DifyTemplateTransformerNodeData]):
        pass
    
    @abstractmethod
    def visit_variable_aggregator(self, node: DifyGraphNode[DifyVariableAggregatorNodeData]):
        pass
    
    @abstractmethod
    def visit_doc_extractor(self, node: DifyGraphNode[DifyDocExtractorNodeData]):
        pass
    
    @abstractmethod
    def visit_edge(self, edge: DifyGraphEdge):
        pass


class DifyNodeVisitor(DifyNodeAbstractVisitor):
    """Concrete visitor for generating node code."""

    # http 节点鉴权 key 的运行时化：URL 前缀 → 环境变量名。
    # 命中前缀的 http 节点，其 api_key 在生成代码里改为 os.getenv(<VAR>)，
    # 而非硬编码明文。以后新增第三方只需在此加一行。
    AUTH_KEY_ENV_BY_URL_PREFIX: dict[str, str] = {
        "https://qianfan.baidubce.com": "QIANFAN_API_KEY",
    }

    def __init__(self, workflow: DifyWorkflow=None, generate_str: str = ""):
        self.workflow = workflow

        self.generate_str = generate_str

        self.node_code_fragments = []
        self.edge_code_fragments = []
        

    def _get_common_args(self, node: DifyGraphNode[DifyNodeDataBase])->dict:
        json_data = node.data.to_json()
        json_data["id"]  = node.id
        json_data["parent_node_id"] = node.parentId

        return json_data
    
    def visit_start(self, node: DifyGraphNode[DifyStartNodeData]):
        """Visit a start node and generate its code."""
        
        print("begin visit start node")

        common_args = self._get_common_args(node)
        code = f'''# create start node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        wf_inputs_data = {self._format_wf_inputs(node.data.wf_inputs)}
        wf_inputs = [WfVariableConfig.from_json(item) for item in wf_inputs_data]
        start_node = StartNode(
            wf_inputs=wf_inputs,
            **common_args
        )
        #self.graph.add_node("{node.id}", start_node)
        self.nodes.append(start_node)
'''
        self.node_code_fragments.append(code)
        
        self._process_edges(node, "start_node")
        
    
    def _process_edges(self, node: DifyGraphNode, node_var_name: str):
        edges = self.workflow.edge_source_target_map[node.id]
        source_node_ids = [item.id for item in self.workflow.edge_target_source_map[node.id]]
        has_fail_branch = False
        fail_next_node_ids = []
        is_branch_node = node.data.type in [WfNodeType.IF_ELSE.value, WfNodeType.QUESTION_CLASSIFIER.value]
        normal_next_node_ids = []
        source_handle_target_map = defaultdict(list)
        is_joint_node = len(source_node_ids) > 1
        
        if ((node.data.type == WfNodeType.START.value 
             or node.data.type == WfNodeType.ITERATION_START.value
             or node.data.type == WfNodeType.LOOP_START.value
            ) and edges == []
        ):
            raise ValueError("start node has not successor node")
        
        for edge in edges:
            if edge.sourceHandle == "fail-branch":
                has_fail_branch = True
                fail_next_node_ids.append(edge.target)
            else:
                normal_next_node_ids.append(edge.target)
            source_handle_target_map[edge.sourceHandle].append(edge.target)

        code = ""
        edge_code = ""
        
        if node.data.type == WfNodeType.START.value:
            edge_code += f'self.graph.add_edge(START, "{node.id}")'


        code += f'\n        {node_var_name}.next_node_ids = {normal_next_node_ids}'
        if has_fail_branch:
            code += f'''\n        {node_var_name}.fail_branch_node_ids = {fail_next_node_ids}
        self.graph.add_node("{node.id}", {node_var_name})
            '''
        elif is_branch_node:
            #code = f'''\n        self.graph.add_node("{node.id}", {node_var_name})'''
            code += f"""
        self.graph.add_node("{node.id}", {node_var_name})
        {node_var_name}.source_handle_target_map ={dict(source_handle_target_map)}
            """
        else:
            # parent_id 非空，说明是在循环或者迭代节点中
            if node.parentId is None:
                code += f'\n        self.graph.add_node("{node.id}", {node_var_name})'
            if (node.data.type not in [
                WfNodeType.LLM.value, WfNodeType.HTTP_REQUEST.value,
                WfNodeType.CODE.value,WfNodeType.TOOL.value
                ] 
                and node.parentId is None
            ):
                edge_code += f"""
        # add edges  source_node={node_var_name}
        #for next_node_id in {normal_next_node_ids}:
        #    self.graph.add_edge("{node.id}", next_node_id)
            """
        self.node_code_fragments.append(code)
        self.edge_code_fragments.append(edge_code)
    
    def visit_classifier(self, node: DifyGraphNode[DifyQuestionClassifierNodeData]):
        """Visit a classifier node and generate its code."""
        print("begin visit classifier node")
        
        common_args = self._get_common_args(node)
        model_config_json = self._format_model_config(node.data.model)

        code = f'''\t        # create classifier node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        classes = []
        classes_config = {self._format_question_classes(node.data.classes)}
        if classes_config:
            for cls in classes_config:
                classes.append(QuestionClassConfig(**cls))
                
        memory_config = {self._format_memory_config(node.data.memory)}
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        vision_config = {self._format_vision_config(node.data.vision)}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])
        
        classifier_node_{node.id} = ClassifierNode(
            instruction="""{getattr(node.data, 'instruction', '')}""",
            query_variable_selector={list(node.data.query_variable_selector)},
            model=LLMNodeModelConfig(**{model_config_json}),
            memory=memory,
            vision=vision,
            classes=classes,
            variables={self._format_variables(node.data.variables)},
            **common_args
        )
        #self.graph.add_node("{node.id}", classifier_node)
        self.nodes.append(classifier_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"classifier_node_{node.id}")
        
    
    def visit_llm(self, node: DifyGraphNode[DifyLLMNodeData]):
        """Visit an LLM node and generate its code."""
        
        print("begin visit llm node")
        
        common_args = self._get_common_args(node)
        model_config_json = self._format_model_config(node.data.model)
        
        code = f'''\n        # create llm node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        memory_config = {self._format_memory_config(node.data.memory)}
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        context_config = {self._format_context_config(node.data.context)}
        context = ContextConfig(**context_config) if context_config else None
        
        prompt_templates = []
        prompt_template_config = {self._format_prompt_template(node.data.prompt_template)}
        if prompt_template_config:
            for pt in prompt_template_config:
                prompt_templates.append(LLmNodePromptTemplate(**pt))
                
        vision_config = {self._format_vision_config(node.data.vision)}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])

        llm_node_{node.id} = LLMNode(
            context=context,
            memory=memory,
            prompt_template=prompt_templates,
            model=LLMNodeModelConfig(**{model_config_json}),
            vision=vision,
            **common_args
        )
        #self.graph.add_node("{node.id}", llm_node)
        self.nodes.append(llm_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"llm_node_{node.id}")
    
    def visit_code(self, node: DifyGraphNode[DifyCodeNodeData]):
        """Visit a code node and generate its code."""
        
        print("begin visit code node")
        
        common_args = self._get_common_args(node)
        code_literal = self._format_code_literal(node.data.code)
        code = f'''\t        # create code node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        code_node_{node.id} = CodeNode(
            {code_literal},
            code_language="{node.data.code_language}",
            outputs={dict(node.data.outputs)},
            **common_args
        )
        #self.graph.add_node("{node.id}", code_node)
        self.nodes.append(code_node_{node.id})
'''
        self.node_code_fragments.append(code)
        
        self._process_edges(node, f"code_node_{node.id}")
    
    def visit_http_request(self, node: DifyGraphNode[DifyHttpRequestNodeData]):
        """Visit an HTTP request node and generate its code."""
        
        print("begin visit http request node")
        
        common_args = self._get_common_args(node)
        body_json_data = self._format_http_request_body(node.data.body)
        auth_json_data = self._format_http_node_authorization(node.data.authorization, node.data.url)
        retry_config_json = self._format_http_request_retry_config(node.data.retry_config)
        timeout_config_json = self._format_http_request_timeout_config(node.data.timeout_config)
        quota_var = "\""
        code = f'''        # create http request node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        body_json_data = {body_json_data}
        auth_json_data = {auth_json_data}
        retry_config_json = {retry_config_json}
        timeout_config_json = {timeout_config_json}
        body = None
        if body_json_data:
            body = HttpRequestBodyConfig()
            body.type = body_json_data.get("type",None)
            body.data = body_json_data.get("data",None)
            if body.data:
                body.data = [HttpRequestBodyConfigItem(**item) for item in body.data]
        
        authorization = None
        if auth_json_data:
            authorization = HttpNodeAuthorizationConfig()
            authorization.type = auth_json_data["type"]
            if auth_json_data.get("config",None):
                authorization.config = HttpNodeApiKeyConfig()
                authorization.config.api_key = auth_json_data["config"].get("api_key",None)
                authorization.config.header = auth_json_data["config"].get("header",None)
                authorization.config.type = auth_json_data["config"].get("type",None)
        
        retry_config = None
        if retry_config_json:
            retry_config = HttpNodeRetryConfig()
            retry_config.max_retries = retry_config_json.get("max_retries",None)
            retry_config.retry_enabled = retry_config_json.get("retry_enabled",None)
            retry_config.retry_interval = retry_config_json.get("retry_interval",None)
        
        timeout_config = None
        if timeout_config_json:
            timeout_config = HttpNodeTimeoutConfig()
            timeout_config.max_connect_timeout = timeout_config_json.get("max_connect_timeout",None)
            timeout_config.max_read_timeout = timeout_config_json.get("max_read_timeout",None)
            timeout_config.max_write_timeout = timeout_config_json.get("max_write_timeout",None)
        
        request_url = {node.data.url if node.data.url.startswith("os.environ") else quota_var + node.data.url + quota_var}
        http_node_{node.id} = HttpRequestNode(

            url=request_url,
            method="{node.data.method}",
            body=body,
            authorization=authorization,
            retry_config=retry_config,
            timeout_config=timeout_config,
            ssl_verify={node.data.ssl_verify},
            params={node.data.params if node.data.params else None},
            headers={node.data.headers if node.data.headers else None},
            **common_args
        )
        #self.graph.add_node("{node.id}", http_node)
        self.nodes.append(http_node_{node.id})
'''
        # 把 api_key 的哨兵 '__ENV_<VAR>__' 替换成裸表达式 os.getenv('<VAR>')，
        # 使生成代码在运行时从环境变量读取密钥（生成文件已 import os）。
        for env_var in self.AUTH_KEY_ENV_BY_URL_PREFIX.values():
            code = code.replace(
                f"'__ENV_{env_var}__'", f"os.getenv('{env_var}')"
            )
        self.node_code_fragments.append(code)

        self._process_edges(node, f"http_node_{node.id}")
    
    def visit_if_else(self, node: DifyGraphNode[DifyIfElseNodeData]):
        """Visit an if-else node and generate its code."""
        
        print("begin visit if else node")
        
        common_args = self._get_common_args(node)
        code = f'''\t        # create ifelse node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        cases_data = {self._format_cases(node.data.cases)}
        cases = []
        for case_data in cases_data:
            case_id = case_data["case_id"]
            logical_operator = case_data["logical_operator"]
            conditions_data = case_data["conditions"]
            conditions = []
            for condition_data in conditions_data:
                sub_variable_condition = None
                if condition_data["sub_variable_condition"]:
                    sub_conditions = []
                    for sub_condition_data in condition_data["sub_variable_condition"]["conditions"]:
                        sub_conditions.append(SubCondition(
                            comparison_operator=sub_condition_data["comparison_operator"],
                            value=sub_condition_data["value"],
                            key=sub_condition_data["key"]
                        ))

                    sub_variable_condition = SubVariableCondition(
                        logical_operator=condition_data["sub_variable_condition"]["logical_operator"],
                        conditions=sub_conditions
                    )
                condition = Condition(
                    variable_selector=condition_data.get("variable_selector",None),
                    comparison_operator=condition_data.get("comparison_operator",None),
                    value=condition_data.get("value",None),
                    varType=condition_data.get("varType",None),
                    sub_variable_condition=sub_variable_condition
                )
                conditions.append(condition)
            case = Case(
                case_id=case_id,
                logical_operator=logical_operator,
                conditions=conditions
            )
            cases.append(case)

        ifelse_node_{node.id} = IfElseNode(
            cases=cases,
            **common_args
        )
        #self.graph.add_node("{node.id}", ifelse_node_{node.id})
        self.nodes.append(ifelse_node_{node.id})
'''
        self.node_code_fragments.append(code)
        
        self._process_edges(node, f"ifelse_node_{node.id}")
        
    def visit_answer(self, node: DifyGraphNode[DifyAnswerNodeData]):
        """Visit an answer node and generate its code."""
        
        print("begin visit answer node")
        
        common_args = self._get_common_args(node)
        code = f'''        # create answer node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        answer_node_{node.id} = AnswerNode(
            answer="""{node.data.answer}""",
            **common_args
        )
        self.nodes.append(answer_node_{node.id})
        '''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"answer_node_{node.id}")
    
    def visit_iteration(self, node: DifyGraphNode[DifyIterationNodeData]):
        """Visit an iteration node and generate its code."""
        
        print("begin visit iteration node")
        
        common_args = self._get_common_args(node)
        code = f'''        # create iteration node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        iteration_node_{node.id} = IterationNode(
            start_node_id="{node.data.start_node_id}",
            iterator_selector={list(node.data.iterator_selector)},
            output_selector={list(node.data.output_selector)},
            output_type="{node.data.output_type}",
            **common_args
        )
        self.nodes.append(iteration_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"iteration_node_{node.id}")
        
    def visit_iteration_start(self, node: DifyGraphNode[DifyIterationStartNodeData]):
        """Visit an iteration start node and generate its code."""
        
        print("begin visit iteration start node")
        
        common_args = self._get_common_args(node)
        code = f'''        # create iteration start node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        iteration_start_node_{node.id} = IterationStartNode(
            **common_args
        )
        self.nodes.append(iteration_start_node_{node.id})
        #self.graph.add_node("{node.id}", iteration_start_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"iteration_start_node_{node.id}")
    
    def visit_loop_start(self, node: DifyGraphNode[DifyLoopStartNodeData]):
        """Visit a loop start node and generate its code."""
        
        print("begin visit loop start node")
        
        common_args = self._get_common_args(node)
        code = f'''        # create loop start node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        loop_start_node_{node.id} = LoopStartNode(
            **common_args
        )
        self.nodes.append(loop_start_node_{node.id})
        self.graph.add_node("{node.id}", loop_start_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"loop_start_node_{node.id}")
        
    def visit_loop_end(self, node: DifyGraphNode[DifyLoopEndNodeData]):
        """Visit a loop end node and generate its code."""
        
        print("begin visit loop end node")
        common_args = self._get_common_args(node)
        code = f'''        # create loop end node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        loop_end_node_{node.id} = LoopEndNode(
            **common_args
        )
        self.nodes.append(loop_end_node_{node.id})
        self.graph.add_node("{node.id}", loop_end_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"loop_end_node_{node.id}")

    
    def visit_loop(self, node: DifyGraphNode[DifyLoopNodeData]):
        """Visit a loop node and generate its code."""
        
        print("begin visit loop node")
        
        common_args = self._get_common_args(node)
        #loop_variables_data = node.data.loop_variables
        loop_variables_data = self._format_loop_variable(node.data.loop_variables)
        code = f'''        # create loop node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        loop_vars = []
        if {loop_variables_data}:
            loop_vars = []
            for loop_var in {loop_variables_data}:
                loop_vars.append(LoopVariableData(
                    id = loop_var.get("id",None),
                    label = loop_var.get("label",None),
                    var_type = loop_var.get("var_type",None),
                    value_type = loop_var.get("value_type",None),
                    value = loop_var.get("value",None)
            ))
        break_conditions = []
        conditions_data = {self._format_conditions(node.data.break_conditions)}
        if conditions_data:
            break_conditions = []
            for condition_data in conditions_data:
                sub_variable_condition = None
                if condition_data["sub_variable_condition"]:
                    sub_conditions = []
                    for sub_condition_data in condition_data["sub_variable_condition"]["conditions"]:
                        sub_conditions.append(SubCondition(
                            comparison_operator=sub_condition_data["comparison_operator"],
                            value=sub_condition_data["value"],
                            key=sub_condition_data["key"]
                        ))

                    sub_variable_condition = SubVariableCondition(
                        logical_operator=condition_data["sub_variable_condition"]["logical_operator"],
                        conditions=sub_conditions
                    )
                condition = Condition(
                    variable_selector=condition_data.get("variable_selector",None),
                    comparison_operator=condition_data.get("comparison_operator",None),
                    value=condition_data.get("value",None),
                    varType=condition_data.get("varType",None),
                    sub_variable_condition=sub_variable_condition
                )
                break_conditions.append(condition)
        loop_node_{node.id} = LoopNode(
            start_node_id="{node.data.start_node_id}",
            error_handle_mode={node.data.error_handle_mode},
            loop_count={node.data.loop_count},
            logical_operator="{node.data.logical_operator}",
            outputs={node.data.outputs},
            loop_variables=loop_vars,
            break_conditions=break_conditions,
            **common_args
        )
        self.nodes.append(loop_node_{node.id})
        #self.graph.add_node("{node.id}", loop_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"loop_node_{node.id}")
    
    def visit_tool(self, node: DifyGraphNode[DifyToolNodeData]):
        """Visit a tool node and generate its code."""
        
        print("begin visit tool node")

        common_args = self._get_common_args(node)
        #tool_parameters_data = node.data.tool_parameters
        #param_schemas_data = node.data.paramSchemas
        param_schemas_data = self._format_param_schemas(node.data.paramSchemas)
        tool_parameters_data = self._format_tool_parameters(node.data.tool_parameters)
        code = f'''        # create tool node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        param_schema = None
        tool_provider_config = ToolProviderConfig()
        if {param_schemas_data}:
            param_schema = [ToolParamSchema.from_json(item) for item in {param_schemas_data}]
        
        tool_provider_config.provider_id = "{node.data.provider_id}"
        tool_provider_config.provider_type = ToolProviderType.value_of("{node.data.provider_type}")
        tool_provider_config.provider_name = "{node.data.provider_name}"
        tool_provider_config.tool_name = "{node.data.tool_name}"
        tool_provider_config.tool_label = "{node.data.tool_label}"
        tool_provider_config.tool_configurations = {node.data.tool_configurations}
        tool_parameters = {{}} 
        for key,item in {tool_parameters_data}.items():
            tool_parameters[key] = ToolInput.from_json2(item)
        tool_provider_config.tool_parameters = tool_parameters

        tool_node_{node.id} = ToolNode(
            is_team_authorization={node.data.is_team_authorization},
            #tool_configurations={node.data.tool_configurations},
            param_schemas=param_schema,
            tool_provider_config=tool_provider_config,
            **common_args,
        )
        self.nodes.append(tool_node_{node.id})
        #self.graph.add_node("{node.id}", tool_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"tool_node_{node.id}")
    
    def visit_knowledge_retrieval(self, node: DifyGraphNode[DifyKnowledgeNodeData]):
        """Visit a knowledge retrieval node and generate its code."""
        print("begin visit knowledge retrieval node")
        
        common_args = self._get_common_args(node)
        code = f'''        # create knowledge retrieval node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        knowledge_node_{node.id} = KnowledgeRetrievalNode(
            **common_args
        )
        self.nodes.append(knowledge_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"knowledge_node_{node.id}")
        
        
    def visit_agent(self, node: DifyGraphNode[DifyAgentNodeData]):
        """Visit a agent node and generate its code."""
        print("begin visit agent node")
        
        common_args = self._get_common_args(node)
        agent_parameters = node.data.agent_parameters
        instruction_data = agent_parameters.get("instruction")
        model_data = agent_parameters["model"].get("value")
        mode_config_json = {
            "mode":model_data.get("mode"),
            "name":model_data.get("model"),
            "provider":model_data.get("provider"),
            "completion_params":model_data.get("completion_params")
        }
        query_data = agent_parameters.get("query")
        #model_config_json = self._format_model_config(model_data)
        tools_data = agent_parameters.get("tools")
        code = f'''        # create agent node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        instruction = ToolInput.from_json2({instruction_data})
        query = ToolInput.from_json2({query_data})
        agent_tool_config = AgentToolConfig()
        tools_type = "{tools_data.get("type")}"
        agent_tool_config.type = tools_type
        tools_value_data = {tools_data.get("value")}
        agent_tool_value_configs = []
        agent_tool_config.value = agent_tool_value_configs
        for item in tools_value_data:
            agent_tool_value_config = AgentToolValueConfig()
            agent_tool_value_configs.append(agent_tool_value_config)
            agent_tool_value_config.enabled = item.get("enabled")
            agent_tool_value_config.extra = item.get("extra")
            agent_tool_value_config.provider_name = item.get("provider_name")
            agent_tool_value_config.settings = item.get("settings")
            agent_tool_value_config.tool_label = item.get("tool_label")
            agent_tool_value_config.tool_name = item.get("tool_name")
            agent_tool_value_config.type = item.get("type")
            parameters_data = item.get("parameters")
            schemas_data = item.get("schemas")
            if parameters_data:
                parameters = {{}}
                for key, value in parameters_data.items():
                    parameters[key] = AgentToolParameterConfig(**value)
                agent_tool_value_config.parameters = parameters
            if schemas_data:
                schemas = []
                for item in schemas_data:
                    schemas.append(ToolParamSchema.from_json(item))
                agent_tool_value_config.schemas = schemas
            
        agent_node_{node.id} = AgentNode(
            instruction=instruction,
            query=query,
            tools=agent_tool_config,
            model=LLMNodeModelConfig(**{mode_config_json}),
            agent_strategy_label="{node.data.agent_strategy_label}",
            agent_strategy_name="{node.data.agent_strategy_name}",
            output_schema="{node.data.output_schema}",
            **common_args
        )
        self.nodes.append(agent_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"agent_node_{node.id}")
        
    def visit_assigner(self, node: DifyGraphNode[DifyVarAssignerNodeData]):
        """Visit a assigner node and generate its code."""
        print("begin visit assigner node")
        common_args = self._get_common_args(node)
        assignments_data = self._format_assignments(node.data.items)
        code = f'''        # create assigner node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        assignments = []
        for item in {assignments_data}:
            var_operation_item = VariableOperationItem()
            var_operation_item.input_type = AssignerInputType.value_of(item["input_type"])
            var_operation_item.operation = AssignerOperation.value_of(item["operation"])
            var_operation_item.variable_selector = item["variable_selector"]
            var_operation_item.value = item["value"]
            #item["value"] = self._format_assigner_value(item["value"])
            assignments.append(var_operation_item)
            
        assigner_node_{node.id} = AssignerNode(
            assignments=assignments,
            **common_args
        )
        self.nodes.append(assigner_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"assigner_node_{node.id}")
        
    def visit_template_transform(self, node: DifyGraphNode[DifyTemplateTransformerNodeData]):
        """Visit a template transform node and generate its code."""
        print("begin visit template transform node")
        common_args = self._get_common_args(node)
        template = node.data.template
        code = f'''        # create template transform node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        template_transform_node_{node.id} = TemplateTransformNode(
            template='{template}',
            **common_args
        )
        self.nodes.append(template_transform_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"template_transform_node_{node.id}")
        
    def visit_variable_aggregator(self, node: DifyGraphNode[DifyVariableAggregatorNodeData]):
        """Visit a variable aggregator node and generate its code."""
        print("begin visit variable aggregator node")
        common_args = self._get_common_args(node)
        advanced_settings_data = self._format_advanced_settings(node.data.advanced_settings)
        group_enabled = advanced_settings_data.get("group_enabled") if advanced_settings_data else None
        groups = advanced_settings_data.get("groups") if advanced_settings_data else []
        code = f'''        # create variable aggregator node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        advanced_settings = None
        if {advanced_settings_data}:
            advanced_settings = AggregatorAdvancedSettings()
            advanced_settings.group_enabled = {group_enabled}
            advanced_settings.groups = []
            for item in {groups}:
                group = AggregatorAdvancedSettings.Group()
                group.group_name = item.get("group_name")
                group.variables = item.get("variables")
                group.output_type = item.get("output_type")
                advanced_settings.groups.append(group)
        variable_aggregator_node_{node.id} = AggregatorNode(
            output_type='{node.data.output_type}',
            variable_selectors={node.data.variable_selectors},
            advanced_settings=advanced_settings,
            **common_args
        )
        self.nodes.append(variable_aggregator_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"variable_aggregator_node_{node.id}")
        
    def visit_doc_extractor(self, node: DifyGraphNode[DifyDocExtractorNodeData]):
        """Visit a doc extractor node and generate its code."""
        print("begin visit doc extractor node")
        common_args = self._get_common_args(node)
        code = f'''        # create doc extractor node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        doc_extractor_node_{node.id} = DocExtractorNode(
            is_array_file={node.data.is_array_file},
            variable_selector={node.data.variable_selector},
            **common_args
        )
        self.nodes.append(doc_extractor_node_{node.id})
'''
        self.node_code_fragments.append(code)
        self._process_edges(node, f"doc_extractor_node_{node.id}")
    
    def visit_generic(self, node: DifyGraphNode):
        """Visit a generic node and generate placeholder code."""
        
        print("begin visit generic node")

        code = f'''        # Generic node: {node.data.title} (Type: {node.data.type})
        # TODO: Implement specific handler for node type: {node.data.type}
'''
        self.node_code_fragments.append(code)
    
    def get_node_code(self) -> str:
        """Get all generated code fragments."""
        return "\n".join(self.node_code_fragments) + "\n" 
    
    def get_edge_code(self) -> str:
        """Get all generated code fragments."""
        return "\n".join(self.edge_code_fragments)+ "\n" 
    
    def visit_edge(self, edge: DifyGraphEdge):
        """Visit an edge and generate its code."""
        
        print("begin visit edge")
        code = f'''        # Edge: {edge.source} -> {edge.target}
        edge = GraphEdge(
            id = "{edge.id}", 
            source = "{edge.source}", 
            source_handle = "{edge.sourceHandle}", 
            target = "{edge.target}",
            target_handle = "{edge.targetHandle}", 
            source_type = "{edge.sourceType}", 
            target_type = "{edge.targetType}", 
            is_in_iteration = {edge.isInIteration},
            is_in_loop = {edge.isInLoop}
        )
        self.append_edge(edge)
'''
        self.edge_code_fragments.append(code)
    
    def visit_end(self, node: DifyGraphNode[DifyEndNodeData]):
        """Visit a end node and generate its code."""
        
        print("begin visit end node")
        common_args = self._get_common_args(node)
        outputs_config = [item.to_json() for item in node.data.outputs]
        code = f'''        # create end node[id={node.id},title={node.data.title}]
        common_args = self._fix_common_args({common_args})
        outputs = [NodeVarConfig.from_json(item) for item in {outputs_config}]
        end_node_{node.id} = EndNode(
            outputs=outputs,
            **common_args
        )
        self.nodes.append(end_node_{node.id})
        self.graph.add_node("{node.id}", end_node_{node.id})
'''
        self.node_code_fragments.append(code)

    
    
    def _format_code_literal(self, code: str) -> str:
        """Format code node source as a readable multiline Python string literal."""
        if code == "":
            return 'code=""'

        # Prefer raw triple-quoted strings so embedded escapes like "\n".join(...) round-trip.
        for delimiter in ('"""', "'''"):
            if delimiter not in code:
                return f"code=r{delimiter}\n{code}\n{delimiter}"

        # Fallback when code contains both triple-quote forms (extremely rare).
        escaped = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'code="{escaped}"'

    # Helper methods for formatting data structures
    def _format_wf_inputs(self, wf_inputs: List[WfVariableConfig]) :
        """Format workflow inputs (simplified)."""
        if not wf_inputs:
            return []
        return [item.to_json() for item in wf_inputs]  # TODO: Implement full formatting
    
    def _format_variables(self, variables) -> str:
        """Format node variables (simplified)."""
        return "None"  # TODO: Implement full formatting
    
    def _format_model_config(self, model:LLMNodeModelConfig) -> dict:
        """Format model configuration (simplified)."""
        return {
            "mode":model.mode,
            "name":model.name,
            "provider":model.provider,
            "completion_params":model.completion_params
        }
    
    def _format_memory_config(self, memory:MemoryConfig) -> dict:
        """Format memory configuration (simplified)."""
        if not memory:
            return None
        
        return {
            "query_prompt_template": memory.query_prompt_template,
            "role_prefix": memory.role_prefix,
            "window":      memory.window
        }
    
    def _format_vision_config(self, vision:VisionConfig) -> dict:
        """Format vision configuration (simplified)."""
        if not vision:
            return None
        
        configs = vision.configs
        
        return {
            "enabled":vision.enabled,
            
            "configs": None if not configs else {
                "variable_selector":configs.variable_selector,
                "detail":configs.detail
            }

        }
    
    def _format_context_config(self, context:ContextConfig) -> dict:
        """Format context configuration (simplified)."""
        return {
            "enabled":context.enabled,
            "variable_selector":context.variable_selector
        }

    
    def _format_prompt_template(self, template:list[LLmNodePromptTemplate]) -> list:
        """Format prompt template (simplified)."""
        if not template:
            return None
        ret = []
        for pt in template:
            ret.append({
                "id":pt.id,
                "role":pt.role,
                "text":pt.text
            })
        return ret
    
    def _format_question_classes(self, classes:list[QuestionClassConfig] ) -> list:
        """Format question classes (simplified)."""
        if not classes:
            return None

        ret = []
        for cls in classes:
            ret.append({
                "name":cls.name,
                "id":cls.id
            })
        return ret
    
    def _format_http_node_authorization(self, auth:Optional[HttpNodeAuthorizationConfig], url:str="") -> dict:
        """Format http node authorization (simplified).

        当 url 命中 AUTH_KEY_ENV_BY_URL_PREFIX 中的前缀时，api_key 用哨兵占位
        (``__ENV_<VAR>__``)，由 visit_http_request 在内联后替换成 os.getenv 表达式，
        以便生成代码在运行时从环境变量读取密钥，而非硬编码明文。
        """
        if not auth:
            return None

        api_key = auth.config.api_key if auth.config else None
        if auth.config and url:
            for prefix, env_var in self.AUTH_KEY_ENV_BY_URL_PREFIX.items():
                if url.startswith(prefix):
                    api_key = f"__ENV_{env_var}__"
                    break

        return {
            "type":auth.type,
            "config":{
                "api_key":api_key ,
                "header":auth.config.header if hasattr(auth.config, "header") else None,
                "type":auth.config.type
            } if auth.config else None
        }

    
    def _format_http_request_body(self, body:Optional[HttpRequestBodyConfig]) -> dict:
        """Format http request body (simplified)."""
        if not body:
            return None
        
        return {
            "type":body.type,
            "data":[{
                "key":item.key,
                "value":item.value,
                "id": item.id,
                "type": item.type
            } for item in body.data] if body.data else None
        }


    def _format_cases(self, cases:list[Case]) -> list:
        """Format cases (simplified)."""
        if not cases:
            raise ValueError("cases is empty")
        
        ret = []
        for case in cases:
            case_id = case.case_id
            logical_operator = case.logical_operator
            conditions = case.conditions
            ret.append({
                "case_id":case_id,
                "logical_operator":logical_operator,
                "conditions":[{
                    "variable_selector":item.variable_selector,
                    "comparison_operator":item.comparison_operator,
                    "value":item.value,
                    "varType":item.varType,
                    "sub_variable_condition":{
                        "logical_operator":item.sub_variable_condition.logical_operator,
                        "conditions":[{
                            "key":item.key,
                            "comparison_operator":item.comparison_operator,
                            "value":item.value
                        } for item in item.sub_variable_condition.conditions]
                    } if item.sub_variable_condition else None
                } for item in conditions]
            })
        return ret
    
    def _format_conditions(self, conditions:list[Condition]) -> list[dict]:
        """Format conditions (simplified)."""
        if not conditions:
            return None
        
        ret = []
        for item in conditions:
            ret.append({
                "variable_selector":item.variable_selector,
                "comparison_operator":item.comparison_operator,
                "value":item.value,
                "varType":item.varType,
                "sub_variable_condition":{
                    "logical_operator":item.sub_variable_condition.logical_operator,
                    "conditions":[{
                        "key":item.key,
                        "comparison_operator":item.comparison_operator,
                        "value":item.value
                        } for item in item.sub_variable_condition.conditions]
                    } if item.sub_variable_condition else None
                } )
            
        return ret

    
    def _format_http_request_retry_config(self, retry_config:Optional[HttpNodeRetryConfig]) -> dict:
        """Format http request retry config (simplified)."""
        if not retry_config:
            return None
        
        return {
            "retry_enabled":retry_config.retry_enabled,
            "max_retries":retry_config.max_retries,
            "retry_interval":retry_config.retry_interval
        }
        
    def _format_http_request_timeout_config(self, timeout_config:Optional[HttpNodeTimeoutConfig]) -> dict:
        """Format http request timeout config (simplified)."""
        if not timeout_config:
            return None
        
        return {
            "max_connect_timeout":timeout_config.max_connect_timeout,
            "max_read_timeout":timeout_config.max_read_timeout,
            "max_write_timeout":timeout_config.max_write_timeout
        }
        
    def _format_loop_variable(self, loop_vars:list[LoopVariableData]) -> dict:
        """Format loop variable (simplified)."""
        if not loop_vars:
            return None
        
        return [
            {
                "id":loop_var.id,
                "label":loop_var.label,
                "var_type":loop_var.var_type,
                "value_type":loop_var.value_type,
                "value":loop_var.value
            } for loop_var in loop_vars
        ]

    def _format_tool_parameters(self, tool_parameters:dict[str, ToolInput]) -> dict:
        """Format tool parameters (simplified)."""
        if not tool_parameters:
            return None
        
        ret = {}
        for key, item in tool_parameters.items():
            ret[key] = {
                "type":item.type,
                "value":item.value,
            }
        return ret
    
    def _format_param_schemas(self, param_schemas:list[ToolParamSchema]) -> list:
        """Format param schemas (simplified)."""
        if not param_schemas:
            return None
        
        ret = []
        for item in param_schemas:
            ret.append({
                "name":item.name,
                "type":item.type,
                "required":item.required,
                "default":item.default,
                "auto_generate":item.auto_generate,
                "form": item.form,
                "human_description":item.human_description,
                "label":item.label,
                "llm_description":item.llm_description,
                "max":item.max,
                "min":item.min,
                "options":item.options,
                "placeholder":item.placeholder,
                "precision":item.precision,
                "scope":item.scope,
                "template":item.template
            })
        return ret
    
    def _format_assignments(self, assignments:list[VariableOperationItem]) -> list:
        """Format assignments (simplified)."""
        if not assignments:
            return None
        
        ret = []
        for item in assignments:
            ret.append({
                "input_type":item.input_type.value,
                "operation":item.operation.value,
                "variable_selector":item.variable_selector,
                "value":item.value
            })
        return ret
    
    def _format_advanced_settings(self, advanced_settings:Optional[AggregatorAdvancedSettings]) -> dict:
        """Format advanced settings (simplified)."""
        if not advanced_settings:
            return None
        
        ret = {}
        if advanced_settings.group_enabled:
            ret["group_enabled"] = advanced_settings.group_enabled
        if advanced_settings.groups:
            ret["groups"] = [{
                "group_name":item.group_name,
                "variables":item.variables,
                "output_type":item.output_type
            } for item in advanced_settings.groups]
        return ret




