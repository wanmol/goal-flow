from typing import List,Optional,Literal,Dict,TypeVar,Generic,Any,Mapping
from collections.abc import  Sequence
from enum import Enum
from copy import deepcopy
import base64
from goalflow.workflow_types import (
    NodeVarConfig,
    DefaultValue,
    VariableOperationItem,
    LLMNodeModelConfig  ,
    QuestionClassConfig,
    MemoryConfig,
    AggregatorAdvancedSettings,
    ContextConfig,
    Condition,
    LLmNodePromptTemplate,
    WfVariableConfig,
    LoopVariableData,
    VisionConfig,
    VisionConfigOptions,
    Case,
    PromptConfig,
    HttpNodeRetryConfig,
    HttpNodeTimeoutConfig,
    HttpRequestBodyConfig,
    HttpNodeAuthorizationConfig,
    ToolInput,
    ToolParamSchema,
    ConversationVar
)
from goalflow.constants import ErrorStrategy,DefaultValueType,ErrorHandleMode

#from collections import defaultdict

        
class DifyWfFeatures:
    
    __slots__ = ["file_upload","opening_statement","retriever_resource","sensitive_word_avoidance","speech_to_text","suggested_questions","suggested_questions_after_answer","text_to_speech"]
    
    file_upload: Dict[str,object]
    opening_statement: str
    retriever_resource: Dict[str,object]
    sensitive_word_avoidance: Dict[str,object]
    speech_to_text: Dict[str,object]
    suggested_questions: List[str]
    suggested_questions_after_answer: Dict[str,object]
    text_to_speech: Dict[str,object]
    
    def __init__(self, * ,file_upload: Dict[str,object],opening_statement: str,retriever_resource: Dict[str,object],sensitive_word_avoidance: Dict[str,object],speech_to_text: Dict[str,object],suggested_questions: List[str],suggested_questions_after_answer: Dict[str,object],text_to_speech: Dict[str,object]) -> None:
        self.file_upload = file_upload
        self.opening_statement = opening_statement
        self.retriever_resource = retriever_resource
        self.sensitive_word_avoidance = sensitive_word_avoidance
        self.speech_to_text = speech_to_text
        self.suggested_questions = suggested_questions
        self.suggested_questions_after_answer = suggested_questions_after_answer
        self.text_to_speech = text_to_speech


class DifyNodeDataBase:
    
    __slots__ = [
        "desc",
        "selected",
        "title",
        "type",
        "variables",
        "isInIteration",
        "isInLoop",
        "iteration_id",
        "loop_id",
        "error_strategy",
        "default_value",
        "parentId"
    ]
    
    desc : str
    selected : bool
    title : str
    type : str
    #input_vars_config : Optional[List[DifyNodeVarConfig]] = None
    variables : Optional[List[NodeVarConfig]] 
    
    isInIteration: Optional[bool] 
    """是否在迭代节点中"""
    
    isInLoop: Optional[bool] 
    """是否在循环节点中"""
    
    iteration_id: Optional[str] 
    
    loop_id: Optional[str] 
    
    parentId: Optional[str] 
    
    error_strategy: Optional[ErrorStrategy] 
    default_value: Optional[list[DefaultValue]] 
    
    def __init__(
        self, 
        * ,
        desc : str, 
        selected : bool, 
        title : str,
        isInIteration : Optional[bool] = None,
        isInLoop : Optional[bool] = None,
        iteration_id : Optional[str] = None,
        loop_id : Optional[str] = None,
        type : str, variables : Optional[List[NodeVarConfig]] = None,
        error_strategy : Optional[str] = None,
        default_value : Optional[list[dict]] = None,
        parentId : Optional[str] = None
    ) -> None:
        self.desc = desc
        self.selected = selected
        self.title = title
        self.type = type
        
        self.isInIteration = isInIteration

        self.isInLoop = isInLoop

        self.iteration_id = iteration_id

        self.loop_id = loop_id
        
        self.parentId = parentId
        
        #if variables is not None:
        self.variables = variables
        
        if error_strategy is not None:
            self.error_strategy = ErrorStrategy.value_of(error_strategy)

        if default_value is not None:
            self.default_value = []
            for item in default_value:
                self.default_value.append(DefaultValue(
                    value = item["value"],
                    type = DefaultValueType.value_of(item["type"]),
                    key = item["key"]
                ))
        
    def to_json(self) -> dict:
        json_data = {
            "desc": self.desc,
            "selected": self.selected,
            "title": self.title,
            "type": self.type,
            "variables": [var.to_json() for var in self.variables] if self.variables else None,
            "isInIteration": self.isInIteration,
            "isInLoop": self.isInLoop,
            "iteration_id": self.iteration_id,
            "loop_id": self.loop_id,
            "error_strategy": self.error_strategy.value if hasattr(self, 'error_strategy') and self.error_strategy else None,
            "default_value": [{
                "value": dv.value,
                "type": dv.type.value,
                "key": dv.key
            } for dv in self.default_value] if hasattr(self, 'default_value') and self.default_value else None
        }
        return {k: v for k, v in json_data.items() if v is not None}
    
    @classmethod
    def from_json(cls, json_data: dict) -> 'DifyNodeDataBase':
        return cls(
            desc=json_data.get("desc", ""),
            selected=json_data.get("selected", False),
            title=json_data.get("title", ""),
            type=json_data.get("type", ""),
            variables=[NodeVarConfig.from_json(var) for var in json_data["variables"]] 
                if "variables" in json_data and json_data["variables"] else None,
            isInIteration=json_data.get("isInIteration"),
            isInLoop=json_data.get("isInLoop"),
            iteration_id=json_data.get("iteration_id"),
            loop_id=json_data.get("loop_id"),
            error_strategy=ErrorStrategy.value_of(json_data.get("error_strategy")) 
                if "error_strategy" in json_data and json_data["error_strategy"] else None,
            default_value=[DefaultValue.from_json(dv) for dv in json_data["default_value"]] 
                if "default_value" in json_data and json_data["default_value"] else None
        )



class DifyStartNodeData(DifyNodeDataBase):
    """
    Start Node Data
    yaml config example:
    - data:
        desc: ''
        selected: false
        title: 开始
        type: start
        variables:
        - label: model
          max_length: 48
          options: []
          required: true
          type: text-input
          variable: model
        - label: networkFlag
          max_length: 48
          options: []
          required: true
          type: number
          variable: networkFlag
        - label: reportYN
          max_length: 48
          options: []
          required: true
          type: number
          variable: reportYN
        - label: deepThinkFlag
          max_length: 48
          options: []
          required: true
          type: number
          variable: deepThinkFlag
        - label: depth
          max_length: 48
          options: []
          required: false
          type: number
          variable: depth
        - label: current_date
          max_length: 48
          options: []
          required: false
          type: text-input
          variable: current_date
        - label: report_template
          max_length: 1024
          options: []
          required: false
          type: paragraph
          variable: report_template
    """
    __slots__ = ["wf_inputs"]
    
    wf_inputs: List[WfVariableConfig]

    def __init__(self, * ,wf_inputs : List[WfVariableConfig], **kwargs) -> None:
        super().__init__(**kwargs)
        self.wf_inputs = wf_inputs
        
 
class DifyLLMNodeData(DifyNodeDataBase):
    __slots__ = ["context","memory","prompt_config","prompt_template","model","vision"]
    context : ContextConfig
    memory : MemoryConfig
    prompt_template : Sequence[LLmNodePromptTemplate]
    prompt_config: Optional[PromptConfig]
    model : LLMNodeModelConfig
    vision : VisionConfig
    
    def __init__(
        self, * ,
        context : ContextConfig,
        memory : MemoryConfig, 
        prompt_template : Sequence[LLmNodePromptTemplate],
        prompt_config: Optional[PromptConfig] = None,
        model : LLMNodeModelConfig, 
        vision : VisionConfig, 
        **kwargs
    ) -> None:
        
        super().__init__(**kwargs)
        self.context = context
        self.memory = memory
        self.prompt_template = prompt_template
        self.prompt_config = prompt_config
        self.model = model
        self.vision = vision

class DifyAnswerNodeData(DifyNodeDataBase) :
    """
    Dify Answer NodeData
    yaml config example:
    - data:
        answer: '{{#1745216597654.text#}}'
        desc: ''
        selected: false
        title: 结束-deepseek-v3
        type: answer
        variables: []
    """
    __slots__ = ["answer"]
    answer: str
    
    def __init__(self, *,answer : str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.answer = answer
        

class DifyCodeNodeData(DifyNodeDataBase):
    __slots__ = ["code","code_language","outputs","output_vars"]
    
    code: str
    """代码文本"""
    code_language: str
    """代码语言,当前只支持python"""
    outputs: dict
    """代码执行输出变量设置"""
    
    # {"var_name1":"string", "var_name2":"int"}
    output_vars : dict
    
    def __init__(self, * ,code : str, code_language : str, outputs : dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.code = code
        self.code_language = code_language
        self.outputs = outputs
        
        self.output_vars = {}
        for var_name,var_config in outputs.items():
            self.output_vars[var_name] = var_config['type']
            
    def safe_check(self) :
        
        return True
            

    
class DifyHttpRequestNodeData(DifyNodeDataBase):
    """
    - data:
        authorization:
          config: null
          type: no-auth
        body:
          data:
          - id: key-value-485
            key: ''
            type: text
            value: '{"goods_name": "{{#1745218103898.goods_name#}}", "indus_name":
              "{{#1745218103898.indus_name#}}"}'
          type: raw-text
        desc: ''
        headers: ''
        method: post
        params: ''
        retry_config:
          max_retries: 3
          retry_enabled: true
          retry_interval: 100
        selected: false
        timeout:
          max_connect_timeout: 0
          max_read_timeout: 0
          max_write_timeout: 0
        title: 行业信息提取
        type: http-request
        url: http://172.26.124.2:8120/industry_rel_find_v3
        variables: []
    """
    __slots__ = [
        "url",
        "method",
        "headers",
        "body",
        "authorization",
        "params",
        "retry_config",
        "timeout_config",
        "ssl_verify"
    ]
    
    url: str
    method: Literal[
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    ]
    headers: dict[str, Any]
    body: Optional[HttpRequestBodyConfig] 
    authorization: HttpNodeAuthorizationConfig
    params: dict[str, Any]
    ssl_verify: Optional[bool] 
    retry_config: Optional[HttpNodeRetryConfig] 
    timeout_config: Optional[HttpNodeTimeoutConfig] 
    
    def __init__(
        self, 
        * ,
        url : str, 
        method : str, 
        headers : dict[str, str], 
        body : HttpRequestBodyConfig, 
        authorization : HttpNodeAuthorizationConfig, 
        params : dict[str, str], 
        ssl_verify : bool,
        retry_config : HttpNodeRetryConfig, 
        timeout_config : HttpNodeTimeoutConfig, 
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        
        self.url = url
        self.method = method
        self.headers = headers
        self.body = body
        self.authorization = authorization
        self.params = params
        self.ssl_verify = ssl_verify
        self.retry_config = retry_config
        self.timeout_config = timeout_config
    
    def assembling_headers(self) -> dict[str, Any]:
        authorization = deepcopy(self.authorization)
        headers = deepcopy(self.headers) or {}
        if self.authorization.type == "api-key":
            if self.authorization.config is None:
                pass
                #raise AuthorizationConfigError("self.authorization config is required")
            if authorization.config is None:
                pass
                #raise AuthorizationConfigError("authorization config is required")

            if self.authorization.config.api_key is None:
                pass
                #raise AuthorizationConfigError("api_key is required")

            if not authorization.config.header:
                authorization.config.header = "Authorization"

            if self.authorization.config.type == "bearer":
                headers[authorization.config.header] = f"Bearer {authorization.config.api_key}"
            elif self.authorization.config.type == "basic":
                credentials = authorization.config.api_key
                if ":" in credentials:
                    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
                else:
                    encoded_credentials = credentials
                headers[authorization.config.header] = f"Basic {encoded_credentials}"
            elif self.authorization.config.type == "custom":
                headers[authorization.config.header] = authorization.config.api_key or ""

        return headers
    

class DifyIfElseNodeData(DifyNodeDataBase):
    """
    If Else Node Data.
    """
    __slots__ = ["logical_operator","conditions","cases"]
    
    logical_operator: Optional[Literal["and", "or"]] 
    conditions: Optional[list[Condition]] 

    cases: Optional[list[Case]] 
    
    def __init__(
        self, 
        * ,
        logical_operator : Optional[Literal["and", "or"]] = "and", 
        conditions : Optional[list[Condition]] = None, 
        cases : Optional[list[Case]] = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.logical_operator = logical_operator
        self.conditions = conditions
        self.cases = cases


KnowledgeSupportedComparisonOperator = Literal[
    # for string or array
    "contains",
    "not contains",
    "start with",
    "end with",
    "is",
    "is not",
    "empty",
    "not empty",
    # for number
    "=",
    "≠",
    ">",
    "<",
    "≥",
    "≤",
    # for time
    "before",
    "after",
]

class KnowledgeMetadataCondition:

    """
    Conditon detail
    """

    name: str
    comparison_operator: KnowledgeSupportedComparisonOperator
    value: str | Sequence[str] | None | int | float = None
            
class MetadataFilteringCondition:
    """
    Metadata Filtering Condition.
    """

    logical_operator: Optional[Literal["and", "or"]] = "and"
    conditions: Optional[list[KnowledgeMetadataCondition]] = None

class RerankingModelConfig:
    """
    Reranking Model Config.
    """

    provider: str
    model: str

class VectorSetting:
    """
    Vector Setting.
    """

    vector_weight: float
    embedding_provider_name: str
    embedding_model_name: str
    
class KeywordSetting:
    """
    Keyword Setting.
    """

    keyword_weight: float
        
class WeightedScoreConfig:
    """
    Weighted score Config.
    """

    vector_setting: VectorSetting
    keyword_setting: KeywordSetting
        
class MultipleRetrievalConfig:
    """
    Multiple Retrieval Config.
    """

    top_k: int
    score_threshold: Optional[float] = None
    reranking_mode: str = "reranking_model"
    reranking_enable: bool = True
    reranking_model: Optional[RerankingModelConfig] = None
    weights: Optional[WeightedScoreConfig] = None
    
class SingleRetrievalConfig:
    """
    Single Retrieval Config.
    """

    model: LLMNodeModelConfig
 
class DifyKnowledgeNodeData(DifyNodeDataBase):
    """
    Knowledge retrieval Node Data.
    
    yaml config example:
    - data:
        dataset_ids:
        - UStt0gZ8Axbqiw/r+uV+ujh1E+7z+VxvU0CwoX37NxqIj9b3hWOZwy8t4e0HmDMK
        - 4+seZZb2T/gDjyprTSivuRzQupR7dUe+Sgy/FQZMy6aErXu55P2gik6RTb65Zarf
        - 72U+ZB1TfLbEfuZxKLINrrvC+Sq2kq2lwNy0ldwNIztnldL5N9kNEzFyO1J+5OhK
        - 9/M6Q/Q+9gneF3CRVvfTX7Sqv2ljVAcypKAaKnwr7EsRuR35OroKpENYp4OJd4xo
        - V8VqY8qq5oFcNedT41XWHtf8BweRm+RWF0Q08wKg48uyeEG8gX/WgnqPptRgMYC1
        - ZTkP+RfCRWrVxHFhKMF31OaIbur5zLOtr7b4il4mPHV+FEpmJ1ZeaNPwdp+dWmL9
        - gg3qmKikwHMqQqCULCmOqlsdI7oeePC0JYZ5nODg0BR91Zm1RW0quHfnKZTy9+ZA
        - jX0fLr7tz0VNT9aiPNRFs8em05HKcOeaX1jHMKvBeyw1RlY6IhRdeJ89x/bHAkJc
        desc: ''
        isInIteration: true
        isInLoop: false
        iteration_id: '1749101964995'
        multiple_retrieval_config:
          reranking_enable: false
          reranking_mode: reranking_model
          reranking_model:
            model: gte-rerank-v2
            provider: langgenius/tongyi/tongyi
          score_threshold: 0.5
          top_k: 5
        query_variable_selector:
        - '1749101964995'
        - item
        retrieval_mode: multiple
        selected: false
        title: 本地检索
        type: knowledge-retrieval
    """
    __slots__ = [
        "dataset_ids",
        "query_variable_selector",
        "retrieval_mode",
        "multiple_retrieval_config",
        "single_retrieval_config",
        "metadata_filtering_mode",
        "metadata_model_config",
        "metadata_filtering_conditions"
    ]
    
    dataset_ids: Sequence[str]   
    """
    知识库数据集id
    """
    
    
    query_variable_selector: Sequence[str]  
    
    retrieval_mode : Literal["single", "multiple"]
    
    multiple_retrieval_config: Optional[MultipleRetrievalConfig] 
    single_retrieval_config: Optional[SingleRetrievalConfig] 
    
    metadata_filtering_mode: Optional[Literal["disabled", "automatic", "manual"]] 
    metadata_model_config: LLMNodeModelConfig
    metadata_filtering_conditions: Optional[MetadataFilteringCondition] 

    def __init__(
        self,
        * ,
        dataset_ids: Sequence[str] = None,
        query_variable_selector: Sequence[str] = None,
        retrieval_mode : Literal["single", "multiple"] = None,
        multiple_retrieval_config: Optional[MultipleRetrievalConfig] = None,
        single_retrieval_config: Optional[SingleRetrievalConfig] = None,
        metadata_filtering_mode: Optional[Literal["disabled", "automatic", "manual"]] = None,
        metadata_model_config: LLMNodeModelConfig = None,
        metadata_filtering_conditions: Optional[MetadataFilteringCondition] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.dataset_ids = dataset_ids


    
class DifyIterationNodeData(DifyNodeDataBase):
    """
    Iteration Node Data.
    yaml config example:
    - data:
        desc: ''
        error_handle_mode: terminated
        height: 608
        is_parallel: false
        iterator_selector:
        - '1749095350742'
        - array
        output_selector:
        - '1749117472269'
        - result
        output_type: array[object]
        parallel_nums: 5
        selected: false
        start_node_id: 1749101964995start
        title: 迭代 2
        type: iteration
        width: 1420
    """
    __slots__ = [
        "start_node_id",
        "parallel_nums",
        "is_parallel",
        "iterator_selector",
        "output_selector",
        "output_type",
        "error_handle_mode"
    ]
    start_node_id: str
    parallel_nums: int 
    is_parallel: bool 
    iterator_selector: Sequence[str]
    output_selector: Sequence[str]
    output_type: str
    error_handle_mode: ErrorHandleMode 
    
    def __init__(
        self, 
        * ,
        start_node_id: str, 
        parallel_nums: int = 5,
        is_parallel: bool = False,
        iterator_selector: Sequence[str],
        output_selector: Sequence[str], 
        output_type: str,
        error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self.start_node_id = start_node_id
        self.parallel_nums = parallel_nums
        self.is_parallel = is_parallel
        self.iterator_selector = iterator_selector
        self.output_selector = output_selector
        self.output_type = output_type
        self.error_handle_mode = error_handle_mode

 
class DifyIterationStartNodeData(DifyNodeDataBase):
    """
    Iteration Start Node Data.
    yaml config example:
    - data:
        desc: ''
        isInIteration: true
        selected: false
        title: ''
        type: iteration-start
    """
    
    isInIteration: bool = True
        
class DifyQuestionClassifierNodeData(DifyNodeDataBase):
    """
    Question Classifier Node Data.
    yaml config example:
    - data:
        classes:
        - id: '1'
          name: 产业相关问题
        - id: '2'
          name: 其它产业无关内容
        desc: ''
        instructions: ''
        model:
          completion_params:
            temperature: 0.7
          mode: chat
          name: qwen2.5-14b-instruct
          provider: langgenius/tongyi/tongyi
        query_variable_selector:
        - '1745215322322'
        - sys.query
        selected: false
        title: 意图识别
        topics: []
        type: question-classifier
        vision:
          enabled: false
    """
    __slots__ = ["instruction","query_variable_selector","model","memory","vision","classes"]
    
    instruction: Optional[str] 
    query_variable_selector: Sequence[str]
    model: LLMNodeModelConfig
    memory: Optional[MemoryConfig] 
    vision: Optional[Dict] 
    classes: list[QuestionClassConfig]    
    
    def __init__(
        self, 
        * ,
        instruction: Optional[str] = None,
        classes: list[QuestionClassConfig] = None,
        query_variable_selector: Sequence[str] = None,
        model: LLMNodeModelConfig = None,
        memory: Optional[MemoryConfig] = None,
        vision: Optional[VisionConfig] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self.instruction = instruction
        self.classes = classes
        self.query_variable_selector = query_variable_selector
        self.model = model
        self.memory = memory
        self.vision = vision

class DifyVarAssignerNodeData(DifyNodeDataBase):
    """
    Variable Assigner Node Data.
    yaml config example:
    - data:
        desc: ''
        items:
        - input_type: variable
          operation: over-write
          value:
          - '17500664461580'
          - current_tme
          variable_selector:
          - conversation
          - currentDate
          write_mode: over-write
        selected: false
        title: 变量赋值 3
        type: assigner
        version: '2'
    """
    __slots__ = ["version","items"]
    
    version: str 
    items: Sequence[VariableOperationItem]

    def __init__(self,*,
        version: str = "2",
        items: Sequence[VariableOperationItem],**kwargs):
        
        super().__init__(**kwargs)
        
        self.version = version
        self.items = items

            
class DifyTemplateTransformerNodeData(DifyNodeDataBase):
    """
    Template Transform Node Data.
    yaml config example:
    - data:
        desc: ''
        isInIteration: true
        isInLoop: false
        iteration_id: '1751609075597'
        selected: false
        template: '{{ "" }}'
        title: Intermediate Output Format
        type: template-transform
        variables: []
    """
    __slots__ = ["template"]
        
    #variables: list[NodeVarConfig]
    template: str    
    def __init__(self,*,template: str,**kwargs):
        super().__init__(**kwargs)
        
        self.template = template

    
class DifyVariableAggregatorNodeData(DifyNodeDataBase):
    """
    Variable Aggregator Node Data.
    yaml config example :
    - data:
        desc: ''
        isInIteration: true
        isInLoop: false
        iteration_id: '1751609075597'
        output_type: string
        selected: false
        title: 变量聚合器
        type: variable-aggregator
        variables:
        - - '1751615974434'
          - output
        - - '1751615945845'
          - output
    """
    __slots__ = ["output_type","variable_selectors","advanced_settings"]
    
    output_type: str
    variable_selectors: list[list[str]]
    advanced_settings: Optional[AggregatorAdvancedSettings] 
    
    def __init__(self,*,output_type: str,variable_selectors: list[list[str]],
                 advanced_settings: Optional[AggregatorAdvancedSettings] = None,
                 **kwargs):
        
        super().__init__(**kwargs)
        self.output_type = output_type
        self.variable_selectors = variable_selectors
        self.advanced_settings = advanced_settings

      

    
class DifyLoopNodeData(DifyNodeDataBase):
    """
    Loop Node Data.
    yaml config example:
    - data:
        break_conditions:
        - comparison_operator: '>'
          id: b8bc0055-01a4-4766-a220-89e3b6248b28
          value: '0'
          varType: number
          variable_selector:
          - '1751631987140'
          - loop
        desc: ''
        error_handle_mode: terminated
        height: 277
        logical_operator: and
        loop_count: 1
        loop_variables:
        - id: 4b85f9ab-2b50-4f3e-9c72-5e080f2db77c
          label: loop
          value: '0'
          value_type: constant
          var_type: number
        selected: false
        start_node_id: 1751631987140start
        title: 循环
        type: loop
        width: 692
    """
    start_node_id: Optional[str] = None
    error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED
    loop_count: int  # Maximum number of loops
    break_conditions: list[Condition]  # Conditions to break the loop
    logical_operator: Literal["and", "or"]
    loop_variables: Optional[list[LoopVariableData]] = None
    outputs: Optional[Mapping[str, Any]] = None
    
    def __init__(self,*,start_node_id: Optional[str] = None,error_handle_mode: ErrorHandleMode = ErrorHandleMode.TERMINATED,
                 loop_count: int,break_conditions: list[Condition],
                 logical_operator: Literal["and", "or"],loop_variables: Optional[list[LoopVariableData]] = None,
                 outputs: Optional[Mapping[str, Any]] = None,**kwargs):
        super().__init__(**kwargs)
        self.start_node_id = start_node_id
        self.error_handle_mode = error_handle_mode
        self.loop_count = loop_count
        self.break_conditions = break_conditions
        self.logical_operator = logical_operator
        self.loop_variables = loop_variables
        self.outputs = outputs

        
class DifyLoopStartNodeData(DifyNodeDataBase):
    """
    Loop Start Node Data.
    yaml config example:
    - data:
        desc: ''
        isInLoop: true
        selected: false
        title: ''
        type: loop-start
    """
    pass

class DifyLoopEndNodeData(DifyNodeDataBase):
    """
    Loop End Node Data.
    yaml config example:
    - data:
        desc: ''
        isInIteration: false
        isInLoop: true
        loop_id: '1754708259616'
        selected: false
        title: 退出循环
        type: loop-end
    """
    pass


class DifyToolNodeData(DifyNodeDataBase):
    """
    Tool Node Data.
    yaml config example:
    desc: ''
        is_team_authorization: true
        output_schema: null
        paramSchemas:
        - auto_generate: null
          default: null
          form: llm
          human_description:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          label:
            en_US: query
            ja_JP: query
            pt_BR: query
            zh_Hans: query
          llm_description: ''
          max: null
          min: null
          name: query
          options: []
          placeholder:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          precision: null
          required: true
          scope: null
          template: null
          type: string
        - auto_generate: null
          default: null
          form: llm
          human_description:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          label:
            en_US: currentDate
            ja_JP: currentDate
            pt_BR: currentDate
            zh_Hans: currentDate
          llm_description: ''
          max: null
          min: null
          name: currentDate
          options: []
          placeholder:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          precision: null
          required: true
          scope: null
          template: null
          type: string
        - auto_generate: null
          default: null
          form: llm
          human_description:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          label:
            en_US: queryInfo
            ja_JP: queryInfo
            pt_BR: queryInfo
            zh_Hans: queryInfo
          llm_description: ''
          max: null
          min: null
          name: queryInfo
          options: []
          placeholder:
            en_US: ''
            ja_JP: ''
            pt_BR: ''
            zh_Hans: ''
          precision: null
          required: true
          scope: null
          template: null
          type: string
        params:
          currentDate: ''
          query: ''
          queryInfo: ''
        provider_id: d8fb6465-756d-4eed-8811-c212270e87a0
        provider_name: 获取钢联数据v2.1
        provider_type: workflow
        selected: false
        title: 获取钢联数据v2.1
        tool_configurations: {}
        tool_label: 获取钢联数据v2.1
        tool_name: getSteel
        tool_parameters:
          currentDate:
            type: mixed
            value: '{{#conversation.currentDate#}}'
          query:
            type: mixed
            value: '{{#sys.query#}}'
          queryInfo:
            type: mixed
            value: '{{#1745218103898.json#}}'
        type: tool
    """
    __slots__ = [
        "is_team_authorization",
        "provider_id",
        "provider_name",
        "provider_type",
        "tool_configurations",
        "tool_label",
        "tool_name",
        "tool_parameters",
        "paramSchemas"
    ]

    is_team_authorization: bool
    provider_id: str
    provider_name: str
    provider_type: str
    tool_configurations: dict
    tool_label: str
    tool_name: str
    tool_parameters: dict[str, ToolInput]
    paramSchemas: list[ToolParamSchema]

    def __init__(
        self,
        *,
        is_team_authorization: Optional[bool] = True,
        provider_id: str,
        provider_name: str,
        provider_type: str,
        tool_configurations: dict,
        tool_label: str,
        tool_name: str,
        tool_parameters: dict[str, ToolInput],
        param_schemas: list[ToolParamSchema],
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self.is_team_authorization = is_team_authorization
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.provider_type = provider_type
        self.tool_configurations = tool_configurations
        self.tool_label = tool_label
        self.tool_name = tool_name
        self.tool_parameters = tool_parameters
        self.paramSchemas = param_schemas

class DifyAgentNodeData(DifyNodeDataBase):
    """
    Agent Node Data.
    yaml config example:
    - data:
        agent_parameters:
          instruction:
            type: constant
            value: "# 钢铁行业数据查询参数提取\n\n您的任务是从用户输入中提取关键时间信息，并转换为标准化的查询参数。请按以下规则处理：\n\
              \n## 提取规则\n1. 时间范围：根据时间描述和当前时间，转换为精确的开始和结束日期。但是如果用户query为预测类型，时间范围应取近期或者当年的数据作为依据。**必须使用代码解释器工具的datetime模块进行计算**。\n\
              2. 如果没有提及时间信息，或存在多个时间段描述，或时间段描述不准确时，按“近期”处理\n\n## 时间处理标准（基于当前日期：[当前日期]）\n\
              - \"最新\"：当前日期或最近可用数据日期\n- \"今天\"：当前日期往前顺延1天\n- \"本月\"：当前月1日至今（月初则顺延至上月）\n\
              - \"上个月\"：上月1日至上月最后一日\n- \"今年\"：当年1月1日至今\n- \"近期\"：当前日期往前推3个月至今\n- \"\
              上周\"：上周一至上周日\n\n## 参数映射\n- dataDateBegin：查询时间范围起始日期（YYYY-MM-DD格式）\n\
              - dataDateEnd：查询时间范围结束日期（YYYY-MM-DD格式）\n\n## 输出要求\n必须返回完整JSON格式，包含所有上述字段，字段类型都为字符串，不能返回列表格式。未提取到的字段置为空字符串(\"\
              \")。日期字段必须使用标准格式YYYY-MM-DD。\n\n## 返回样例\n{\n  \"dataDateBegin\": \"（YYYY-MM-DD格式）\"\
              ,\n  \"dataDateEnd\": \"（YYYY-MM-DD格式）\",\n}"
          model:
            type: constant
            value:
              completion_params: {}
              mode: chat
              model: gpt-4o
              model_type: llm
              provider: langgenius/azure_openai/azure_openai
              type: model-selector
          query:
            type: constant
            value: '用户的输入是{{#1752129147346.query#}}。当前时间是{{#1752129147346.current_date#}}。


              您的任务是从用户输入中提取关键时间信息，并转换为标准化的查询参数。'
          tools:
            type: constant
            value:
            - enabled: true
              extra:
                description: ''
              parameters:
                code:
                  auto: 1
                  value: null
                language:
                  auto: 1
                  value: null
              provider_name: code
              schemas:
              - auto_generate: null
                default: null
                form: llm
                human_description:
                  en_US: The programming language of the code
                  ja_JP: The programming language of the code
                  pt_BR: A linguagem de programação do código
                  zh_Hans: 代码的编程语言
                label:
                  en_US: Language
                  ja_JP: Language
                  pt_BR: Idioma
                  zh_Hans: 语言
                llm_description: language of the code, only "python3" and "javascript"
                  are supported
                max: null
                min: null
                name: language
                options:
                - label:
                    en_US: Python3
                    ja_JP: Python3
                    pt_BR: Python3
                    zh_Hans: Python3
                  value: python3
                - label:
                    en_US: JavaScript
                    ja_JP: JavaScript
                    pt_BR: JavaScript
                    zh_Hans: JavaScript
                  value: javascript
                placeholder: null
                precision: null
                required: true
                scope: null
                template: null
                type: string
              - auto_generate: null
                default: null
                form: llm
                human_description:
                  en_US: The code to be executed
                  ja_JP: The code to be executed
                  pt_BR: O código a ser executado
                  zh_Hans: 要执行的代码
                label:
                  en_US: Code
                  ja_JP: Code
                  pt_BR: Código
                  zh_Hans: 代码
                llm_description: code to be executed, only native packages are allowed,
                  network/IO operations are disabled.
                max: null
                min: null
                name: code
                options: []
                placeholder: null
                precision: null
                required: true
                scope: null
                template: null
                type: string
              settings: {}
              tool_label: 代码解释器
              tool_name: simple_code
              type: builtin
        agent_strategy_label: FunctionCalling
        agent_strategy_name: function_calling
        agent_strategy_provider_name: langgenius/agent/agent
        desc: ''
        output_schema: null
        plugin_unique_identifier: langgenius/agent:0.0.15@89d496aa9b23fcd1ef9add8cfcbadeaeb4eb5c30ff8d76f7e6c9d59c46d2e2f5
        selected: false
        title: Get_Date_Range
        type: agent
    """
    __slots__ = ["agent_parameters","agent_strategy_label","agent_strategy_name","agent_strategy_provider_name","desc","output_schema","plugin_unique_identifier","selected","title"]
    agent_parameters : dict[str,any]
    agent_strategy_label : str
    agent_strategy_name : str
    agent_strategy_provider_name : str
    desc : str
    output_schema : dict[str,any]
    plugin_unique_identifier : str
    selected : bool
    title : str
    def __init__(
        self,
        *,
        agent_parameters: dict[str,any],
        agent_strategy_label: str,
        agent_strategy_name: str,
        agent_strategy_provider_name: str,
        output_schema: dict[str,any],
        plugin_unique_identifier: str,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.agent_parameters = agent_parameters
        self.agent_strategy_label = agent_strategy_label
        self.agent_strategy_name = agent_strategy_name
        self.agent_strategy_provider_name = agent_strategy_provider_name
        self.output_schema = output_schema
        self.plugin_unique_identifier = plugin_unique_identifier


class DifyDocExtractorNodeData(DifyNodeDataBase):
    """
    End Node Data.
    yaml config example:
    - data:
        desc: ''
        is_array_file: true
        selected: false
        title: 文档提取器
        type: document-extractor
        variable_selector:
        - '1749536977748'
        - files
    """
    __slots__ = ["is_array_file","variable_selector"]
    is_array_file : bool
    variable_selector : list[str]
    def __init__(self,*,is_array_file: bool,variable_selector: list[str],**kwargs):
        super().__init__(**kwargs)
        self.is_array_file = is_array_file
        self.variable_selector = variable_selector

class DifyEndNodeData(DifyNodeDataBase):
    """
    End Node Data.
    yaml config example:
    - data:
        desc: ''
        outputs:
        - value_selector:
          - '1755582789731'
          - result
          value_type: array[object]
          variable: result
        selected: true
        title: 结束
        type: end
    """
    __slots__ = ["outputs"]
    
    outputs : list[NodeVarConfig]

    def __init__(self,*,outputs: list[NodeVarConfig],**kwargs):
        super().__init__(**kwargs)
        self.outputs = outputs


        
NodeData = TypeVar("NodeData",bound=DifyNodeDataBase, covariant=True)

NodePosition = Literal["top","right","bottom","left"]

class DifyGraphNode(Generic[NodeData]):
    __slots__ = ["data","id","height","width","position",
                 "positionAbsolute","selected","sourcePosition",
                 "targetPosition","type","parentId"]

    
    data: NodeData
    id: str
    parentId: Optional[str] 
    height: int
    width: int
    position: dict[str,int]
    positionAbsolute: dict[str,int]
    selected: bool
    sourcePosition: NodePosition
    targetPosition: NodePosition
    type: str

    def __init__(self, * ,data : NodeData, id : str, height : int, width : int, 
                 position : dict[str,int], positionAbsolute : dict[str,int], selected : bool,
                 sourcePosition : NodePosition, targetPosition : NodePosition, type : str, parentId : Optional[str] = None) -> None:

        self.data = data
        self.id = id
        self.height = height
        self.width = width
        self.position = position
        self.positionAbsolute = positionAbsolute
        self.selected = selected
        self.sourcePosition = sourcePosition
        self.targetPosition = targetPosition
        self.type = type
        self.parentId = parentId
        
    def accept(self,visitor: "DifyNodeVisitor"):
        visitor.visit(self)
        
    def __str__(self) -> str:
        return f"DifyNode(id={self.id}, type={self.type}, data={self.data}, parentId={self.parentId})"

class DifyGraphEdge:
    """
    Dify Graph Edge.
    """
    __slots__ = [
        "id",
        "source",
        "sourceHandle",
        "target",
        "targetHandle",
        "sourceType",
        "targetType",
        "isInIteration",
        "isInLoop",
        "selected",
        "type"
    ]
    id: str
    soruce: str
    """source node id"""
    sourceHandle: str
    target: str
    """target node id"""
    targetHandle: str
    sourceType: str
    """source node type"""
    targetType: str
    """target node type"""
    isInIteration: Optional[bool] 
    isInLoop: Optional[bool] 
    selected: Optional[bool]
    type: str
    def __init__(self, * ,id : str, source : str, sourceHandle : str, target : str,
                 targetHandle : str, sourceType : str, targetType : str, isInIteration : Optional[bool] = None,
                 isInLoop : Optional[bool] = None, selected : Optional[bool] = None, type : str) -> None:
        self.id = id
        self.source = source
        self.sourceHandle = sourceHandle
        self.target = target
        self.targetHandle = targetHandle
        self.sourceType = sourceType
        self.targetType = targetType
        self.isInIteration = isInIteration
        self.isInLoop = isInLoop
        self.selected = selected
        self.type = type

DIFY_APP_MODE_WORKFLOW = "workflow"
DIFY_APP_MODE_ADVANCED_CHATFLOW = "advanced-chat"

        

    