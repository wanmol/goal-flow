from typing import Dict, Any
from goalflow.state import GenericState,BaseState
from langgraph.graph import StateGraph,START
from goalflow.node import *
from goalflow.dify_parser.dify_types import *
from goalflow.workflow_types import *
from goalflow.constants import *
from typing import Iterator,Any
from goalflow.workflow.base_workflow import BaseWorkflow,GraphEdge
import os

class GeneratedWorkflow_1755689716614(BaseWorkflow[BaseState]):
    """Generated workflow for: 1755689716614"""
    
    def __init__(self,config_schema:str=None,workflow_type:str="chatflow"):
        super().__init__(config_schema, workflow_type)
    
    def _setup_environment_variables(self):
        "auto bind all environment variables"
        
        environment_list = []
        for env in []:
            environment_list.append(EnvironmentVariable.from_json(env))
        self.environment_list = environment_list
        
        
    def _setup_conversation_variables(self):
        "auto bind all conversation variables"
        
        conversation_list = []
        for conv in [{'description': '', 'name': 'test_int', 'id': 'e173fdb6-26c5-4225-9147-14634fcaa73e', 'value': 1, 'value_type': 'integer', 'selector': ['conversation', 'test_int']}]:
            conversation_list.append(ConversationVar.from_json(conv))
        self.conversation_list = conversation_list
        
    
    def _setup_nodes(self):
        """Setup all workflow nodes"""
        # create start node[id=1755689716614,title=开始]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '开始', 'type': 'start', 'isInIteration': False, 'isInLoop': False, 'id': '1755689716614', 'parent_node_id': None})
        wf_inputs_data = []
        wf_inputs = [WfVariableConfig.from_json(item) for item in wf_inputs_data]
        start_node = StartNode(
            wf_inputs=wf_inputs,
            **common_args
        )
        #self.graph.add_node("1755689716614", start_node)
        self.nodes.append(start_node)


        start_node.next_node_ids = ['1756044135146']
        self.graph.add_node("1755689716614", start_node)
        # create iteration node[id=1756023315127,title=迭代]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '迭代', 'type': 'iteration', 'isInIteration': False, 'isInLoop': False, 'id': '1756023315127', 'parent_node_id': None})
        iteration_node_1756023315127 = IterationNode(
            start_node_id="1756023315127start",
            iterator_selector=['1756045587974', 'array'],
            output_selector=['1756046176566', 'result'],
            output_type="array[string]",
            **common_args
        )
        self.nodes.append(iteration_node_1756023315127)


        iteration_node_1756023315127.next_node_ids = ['1756189035885']
        self.graph.add_node("1756023315127", iteration_node_1756023315127)
        # create iteration start node[id=1756023315127start,title=]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '', 'type': 'iteration-start', 'isInIteration': True, 'isInLoop': False, 'id': '1756023315127start', 'parent_node_id': '1756023315127'})
        iteration_start_node_1756023315127start = IterationStartNode(
            **common_args
        )
        self.nodes.append(iteration_start_node_1756023315127start)
        #self.graph.add_node("1756023315127start", iteration_start_node_1756023315127start)


        iteration_start_node_1756023315127start.next_node_ids = ['1756045841366']
	        # create classifier node[id=1756044135146,title=联网意图识别]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '联网意图识别', 'type': 'question-classifier', 'isInIteration': False, 'isInLoop': False, 'id': '1756044135146', 'parent_node_id': None})
        classes = []
        classes_config = [{'name': '需要联网搜索的问题', 'id': '1'}, {'name': '不需要联网搜索的问题', 'id': '2'}]
        if classes_config:
            for cls in classes_config:
                classes.append(QuestionClassConfig(**cls))
                
        memory_config = None
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        vision_config = {'enabled': False, 'configs': None}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])
        
        classifier_node_1756044135146 = ClassifierNode(
            instruction="""None""",
            query_variable_selector=['1755689716614', 'sys.query'],
            model=LLMNodeModelConfig(**{'mode': 'chat', 'name': 'deepseek-v4-flash', 'provider': 'langgenius/tongyi/tongyi', 'completion_params': {'temperature': 0.7}}),
            memory=memory,
            vision=vision,
            classes=classes,
            variables=None,
            **common_args
        )
        #self.graph.add_node("1756044135146", classifier_node)
        self.nodes.append(classifier_node_1756044135146)


        classifier_node_1756044135146.next_node_ids = ['1756045460846', '1756046728919']
        self.graph.add_node("1756044135146", classifier_node_1756044135146)
        classifier_node_1756044135146.source_handle_target_map ={'1': ['1756045460846'], '2': ['1756046728919']}
            

        # create llm node[id=1756045460846,title=问题改写]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '问题改写', 'type': 'llm', 'isInIteration': False, 'isInLoop': False, 'id': '1756045460846', 'parent_node_id': None})
        memory_config = None
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        context_config = {'enabled': False, 'variable_selector': []}
        context = ContextConfig(**context_config) if context_config else None
        
        prompt_templates = []
        prompt_template_config = [{'id': '74d59a93-ee97-4cb4-a976-a6fe38ea2880', 'role': 'system', 'text': '# 智能问题改写系统\n\n## 角色定位\n您是一位专业的语义改写专家，能够保持原意的前提下优化用户问题表达。\n\n## 任务说明\n分析用户输入的问题，判断是否需要改写以及需要生成的改写版本数量（最多3个）。\n改写时可参考用户提供的上下游信息和私域知识库内容，确保改写版本：\n- 保持原始问题的核心意图不变\n- 每个版本表达方式互不相同\n- 均以问句形式呈现\n\n## 判断标准\n- 是否需要改写：评估原问题的清晰度、准确性和完整性\n- 改写数量：根据问题复杂度和可能的表达方式确定（1-3个）\n\n## 输出要求\n必须返回JSON格式，其中result字段必须是列表，包含用户原始query和所有改写结果：\n{\n    "result": [ "改写版本1", "改写版本2", "..."]\n}'}, {'id': '3101e2c8-207f-4f8e-98d9-4e645409e680', 'role': 'user', 'text': '用户的问题：{{#sys.query#}}。当前的时间是2025-08-26'}]
        if prompt_template_config:
            for pt in prompt_template_config:
                prompt_templates.append(LLmNodePromptTemplate(**pt))
                
        vision_config = {'enabled': False, 'configs': None}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])

        llm_node_1756045460846 = LLMNode(
            context=context,
            memory=memory,
            prompt_template=prompt_templates,
            model=LLMNodeModelConfig(**{'mode': 'chat', 'name': 'deepseek-v4-flash', 'provider': 'langgenius/tongyi/tongyi', 'completion_params': {'enable_thinking': False}}),
            vision=vision,
            **common_args
        )
        #self.graph.add_node("1756045460846", llm_node)
        self.nodes.append(llm_node_1756045460846)


        llm_node_1756045460846.next_node_ids = ['1756045587974']
        self.graph.add_node("1756045460846", llm_node_1756045460846)
	        # create code node[id=1756045587974,title=代码执行]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '代码执行', 'type': 'code', 'variables': [{'variable': 'text', 'value_selector': ['1756045460846', 'text']}], 'isInIteration': False, 'isInLoop': False, 'id': '1756045587974', 'parent_node_id': None})
        code_node_1756045587974 = CodeNode(
            code=r"""

import json
def main(text: str) -> dict:
    if text.startswith('```json'):
        text = text[7:-3]
    result = json.loads(text)
    array = result['result']
    depth = len(array)
    return {
        "array": array,
        "depth": depth
    }

""",
            code_language="python3",
            outputs={'array': {'children': None, 'type': 'array[string]'}, 'depth': {'children': None, 'type': 'number'}},
            **common_args
        )
        #self.graph.add_node("1756045587974", code_node)
        self.nodes.append(code_node_1756045587974)


        code_node_1756045587974.next_node_ids = ['1756023315127']
        self.graph.add_node("1756045587974", code_node_1756045587974)
        # create http request node[id=1756045841366,title=HTTP 请求]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': 'HTTP 请求', 'type': 'http-request', 'isInIteration': True, 'isInLoop': False, 'iteration_id': '1756023315127', 'id': '1756045841366', 'parent_node_id': '1756023315127'})
        body_json_data = {'type': 'json', 'data': [{'key': '', 'value': '{\n    "messages": [\n        {\n            "content": "{{#1756023315127.item#}}",\n            "role": "user"\n        }\n    ],\n"resource_type_filter": [\n{"type": "web", "top_k": 5}\n]\n}', 'id': 'key-value-427', 'type': 'text'}]}
        auth_json_data = {'type': 'api-key', 'config': {'api_key': os.getenv('QIANFAN_API_KEY'), 'header': None, 'type': 'bearer'}}
        retry_config_json = {'retry_enabled': True, 'max_retries': 3, 'retry_interval': 100}
        timeout_config_json = {'max_connect_timeout': 0, 'max_read_timeout': 0, 'max_write_timeout': 0}
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
        
        request_url = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
        http_node_1756045841366 = HttpRequestNode(

            url=request_url,
            method="post",
            body=body,
            authorization=authorization,
            retry_config=retry_config,
            timeout_config=timeout_config,
            ssl_verify=True,
            params=None,
            headers={'Content-Type': 'application/json'},
            **common_args
        )
        #self.graph.add_node("1756045841366", http_node)
        self.nodes.append(http_node_1756045841366)


        http_node_1756045841366.next_node_ids = ['1756046176566']
	        # create code node[id=1756046176566,title=代码执行 2]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '代码执行 2', 'type': 'code', 'variables': [{'variable': 'res', 'value_selector': ['1756045841366', 'body']}, {'variable': 'req', 'value_selector': ['1756023315127', 'item']}], 'isInIteration': True, 'isInLoop': False, 'iteration_id': '1756023315127', 'id': '1756046176566', 'parent_node_id': '1756023315127'})
        code_node_1756046176566 = CodeNode(
            code=r"""

import json
def main(res: str, req: str) -> dict:
    data = {"search_topic":req,"search_result": res}
    return {
        "result": json.dumps(data, ensure_ascii=False),
    }

""",
            code_language="python3",
            outputs={'result': {'children': None, 'type': 'string'}},
            **common_args
        )
        #self.graph.add_node("1756046176566", code_node)
        self.nodes.append(code_node_1756046176566)


        code_node_1756046176566.next_node_ids = []

        # create llm node[id=1756046349071,title=信息整合回答]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '信息整合回答', 'type': 'llm', 'isInIteration': False, 'isInLoop': False, 'id': '1756046349071', 'parent_node_id': None})
        memory_config = None
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        context_config = {'enabled': False, 'variable_selector': []}
        context = ContextConfig(**context_config) if context_config else None
        
        prompt_templates = []
        prompt_template_config = [{'id': '499e35ce-bda6-4071-982a-a405ab088f02', 'role': 'system', 'text': '你是一个ai助手，请耐心回答用户的问题。整合用户问题以及联网搜索结果，给出用户问题的最终答案'}, {'id': '21379567-f452-4cfe-a8f8-a70b1bb11921', 'role': 'user', 'text': '##下面是用户的问题 ：\n【{{#sys.query#}}】\n\n##联网搜索的结果\n【{{#1756189035885.result#}}】 '}]
        if prompt_template_config:
            for pt in prompt_template_config:
                prompt_templates.append(LLmNodePromptTemplate(**pt))
                
        vision_config = {'enabled': False, 'configs': None}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])

        llm_node_1756046349071 = LLMNode(
            context=context,
            memory=memory,
            prompt_template=prompt_templates,
            model=LLMNodeModelConfig(**{'mode': 'chat', 'name': 'deepseek-v4-flash', 'provider': 'langgenius/tongyi/tongyi', 'completion_params': {}}),
            vision=vision,
            **common_args
        )
        #self.graph.add_node("1756046349071", llm_node)
        self.nodes.append(llm_node_1756046349071)


        llm_node_1756046349071.next_node_ids = ['1756046662447']
        self.graph.add_node("1756046349071", llm_node_1756046349071)
        # create answer node[id=1756046662447,title=直接回复]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '直接回复', 'type': 'answer', 'isInIteration': False, 'isInLoop': False, 'id': '1756046662447', 'parent_node_id': None})
        answer_node_1756046662447 = AnswerNode(
            answer="""{{#1756046349071.text#}}""",
            **common_args
        )
        self.nodes.append(answer_node_1756046662447)
        

        answer_node_1756046662447.next_node_ids = []
        self.graph.add_node("1756046662447", answer_node_1756046662447)

        # create llm node[id=1756046728919,title=不联网直接回答]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '不联网直接回答', 'type': 'llm', 'isInIteration': False, 'isInLoop': False, 'id': '1756046728919', 'parent_node_id': None})
        memory_config = None
        memory = MemoryConfig(**memory_config) if memory_config else None
        
        context_config = {'enabled': False, 'variable_selector': []}
        context = ContextConfig(**context_config) if context_config else None
        
        prompt_templates = []
        prompt_template_config = [{'id': '4f1ed4e5-4f95-4980-aef8-7ba6236f6d2b', 'role': 'system', 'text': '你是一个ai助手。 用户的问题不需要联网查找资料，可以直接回答'}]
        if prompt_template_config:
            for pt in prompt_template_config:
                prompt_templates.append(LLmNodePromptTemplate(**pt))
                
        vision_config = {'enabled': False, 'configs': None}
        vision = None
        if vision_config:
            vision = VisionConfig(enabled=vision_config.get("enabled",False))
            if "configs" in vision_config and vision_config["configs"]:
                vision.configs = VisionConfigOptions(**vision_config["configs"])

        llm_node_1756046728919 = LLMNode(
            context=context,
            memory=memory,
            prompt_template=prompt_templates,
            model=LLMNodeModelConfig(**{'mode': 'chat', 'name': 'deepseek-v4-flash', 'provider': 'langgenius/tongyi/tongyi', 'completion_params': {'temperature': 0.7}}),
            vision=vision,
            **common_args
        )
        #self.graph.add_node("1756046728919", llm_node)
        self.nodes.append(llm_node_1756046728919)


        llm_node_1756046728919.next_node_ids = ['1756046787448']
        self.graph.add_node("1756046728919", llm_node_1756046728919)
        # create answer node[id=1756046787448,title=直接回复 2]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '直接回复 2', 'type': 'answer', 'isInIteration': False, 'isInLoop': False, 'id': '1756046787448', 'parent_node_id': None})
        answer_node_1756046787448 = AnswerNode(
            answer="""{{#1756046728919.text#}}""",
            **common_args
        )
        self.nodes.append(answer_node_1756046787448)
        

        answer_node_1756046787448.next_node_ids = []
        self.graph.add_node("1756046787448", answer_node_1756046787448)
	        # create code node[id=1756189035885,title=代码执行 3]
        common_args = self._fix_common_args({'desc': '', 'selected': False, 'title': '代码执行 3', 'type': 'code', 'variables': [{'variable': 'items', 'value_selector': ['1756023315127', 'output']}], 'isInIteration': False, 'isInLoop': False, 'id': '1756189035885', 'parent_node_id': None})
        code_node_1756189035885 = CodeNode(
            code=r"""

import json
def main(items: list) -> dict:
    result = f"本次联网搜索结果为{len(items)}条，结果为："
    return {
        "result": result + json.dumps(items, ensure_ascii=False),
    }

""",
            code_language="python3",
            outputs={'result': {'children': None, 'type': 'string'}},
            **common_args
        )
        #self.graph.add_node("1756189035885", code_node)
        self.nodes.append(code_node_1756189035885)


        code_node_1756189035885.next_node_ids = ['1756046349071']
        self.graph.add_node("1756189035885", code_node_1756189035885)

        
    def _setup_edges(self):
        """Setup all workflow edges"""
        self.graph.add_edge(START, "1755689716614")
        # add edges  source_node=start_node
        #for next_node_id in ['1756044135146']:
        #    self.graph.add_edge("1755689716614", next_node_id)
            

        # add edges  source_node=iteration_node_1756023315127
        #for next_node_id in ['1756189035885']:
        #    self.graph.add_edge("1756023315127", next_node_id)
            








        # add edges  source_node=answer_node_1756046662447
        #for next_node_id in []:
        #    self.graph.add_edge("1756046662447", next_node_id)
            


        # add edges  source_node=answer_node_1756046787448
        #for next_node_id in []:
        #    self.graph.add_edge("1756046787448", next_node_id)
            

        # Edge: 1755689716614 -> 1756044135146
        edge = GraphEdge(
            id = "1755689716614-source-1756044135146-target", 
            source = "1755689716614", 
            source_handle = "source", 
            target = "1756044135146",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756044135146 -> 1756045460846
        edge = GraphEdge(
            id = "1756044135146-1-1756045460846-target", 
            source = "1756044135146", 
            source_handle = "1", 
            target = "1756045460846",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756045460846 -> 1756045587974
        edge = GraphEdge(
            id = "1756045460846-source-1756045587974-target", 
            source = "1756045460846", 
            source_handle = "source", 
            target = "1756045587974",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756045587974 -> 1756023315127
        edge = GraphEdge(
            id = "1756045587974-source-1756023315127-target", 
            source = "1756045587974", 
            source_handle = "source", 
            target = "1756023315127",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756023315127start -> 1756045841366
        edge = GraphEdge(
            id = "1756023315127start-source-1756045841366-target", 
            source = "1756023315127start", 
            source_handle = "source", 
            target = "1756045841366",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756045841366 -> 1756046176566
        edge = GraphEdge(
            id = "1756045841366-source-1756046176566-target", 
            source = "1756045841366", 
            source_handle = "source", 
            target = "1756046176566",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756046349071 -> 1756046662447
        edge = GraphEdge(
            id = "1756046349071-source-1756046662447-target", 
            source = "1756046349071", 
            source_handle = "source", 
            target = "1756046662447",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756044135146 -> 1756046728919
        edge = GraphEdge(
            id = "1756044135146-2-1756046728919-target", 
            source = "1756044135146", 
            source_handle = "2", 
            target = "1756046728919",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756046728919 -> 1756046787448
        edge = GraphEdge(
            id = "1756046728919-source-1756046787448-target", 
            source = "1756046728919", 
            source_handle = "source", 
            target = "1756046787448",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756023315127 -> 1756189035885
        edge = GraphEdge(
            id = "1756023315127-source-1756189035885-target", 
            source = "1756023315127", 
            source_handle = "source", 
            target = "1756189035885",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)

        # Edge: 1756189035885 -> 1756046349071
        edge = GraphEdge(
            id = "1756189035885-source-1756046349071-target", 
            source = "1756189035885", 
            source_handle = "source", 
            target = "1756046349071",
            target_handle = "target", 
            source_type = "None", 
            target_type = "None", 
            is_in_iteration = False,
            is_in_loop = False
        )
        self.append_edge(edge)


    
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
