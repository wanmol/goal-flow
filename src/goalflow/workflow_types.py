from typing import Any, List, Sequence, Literal, Dict, Optional, Union, Callable

from pydantic import BaseModel

from langgraph.types import Interrupt

from goalflow.constants import (
    DefaultValueType,
    AssignerInputType,
    AssignerOperation,
    VariableEntityType,
    FileTransferMethod,
    FileType,
    ToolProviderType,
)
from enum import Enum



class NodeVarConfig:
    """input parameter config of a dify node"""

    variable: str
    """new name of the variable within this node"""

    value_selector: List[str]
    """
    source of the variable value, in the format ['17490117806280', 'result']
    where 17490117806280 is the source node id, and result is the output variable name of the source node
    """

    value_type: Optional[str]

    __slots__ = ["variable", "value_selector", "value_type"]

    def __init__(
        self,
        *,
        variable: str,
        value_selector: List[str],
        value_type: Optional[str] = None,
    ) -> None:
        self.variable = variable
        self.value_selector = value_selector
        self.value_type = value_type

    def to_json(self):
        ret = {"variable": self.variable, "value_selector": self.value_selector}
        if self.value_type:
            ret["value_type"] = self.value_type
        return ret

    @classmethod
    def from_json(cls, json_data: dict) -> "NodeVarConfig":
        if "variable" not in json_data:
            raise ValueError("variable not found")

        if "value_selector" not in json_data:
            raise ValueError("value_selector not found")

        if not isinstance(json_data["value_selector"], list):
            raise ValueError("value_selector must be list")

        return cls(
            variable=json_data.get("variable", ""),
            value_selector=json_data.get("value_selector", []),
            value_type=json_data.get("value_type", None),
        )


class EnvironmentVariable:
    __slots__ = ["description", "id", "name", "selector", "value", "value_type"]

    def __init__(
        self,
        *,
        description: str,
        id: str,
        name: str,
        selector: list[str],
        value: str,
        value_type: str,
    ) -> None:
        self.description = description
        self.id = id
        self.name = name
        self.selector = selector
        self.value = value
        self.value_type = value_type

    def to_json(self):
        return {
            "description": self.description,
            "id": self.id,
            "name": self.name,
            "selector": self.selector,
            "value": self.value,
            "value_type": self.value_type,
        }

    @staticmethod
    def from_json(json_data: dict) -> "EnvironmentVariable":
        if "description" not in json_data:
            raise ValueError("description not found")

        if "id" not in json_data:
            raise ValueError("id not found")

        if "name" not in json_data:
            raise ValueError("name not found")

        if "selector" not in json_data:
            raise ValueError("selector not found")

        if "value" not in json_data:
            raise ValueError("value not found")

        if "value_type" not in json_data:
            raise ValueError("value_type not found")

        return EnvironmentVariable(
            description=json_data.get("description", ""),
            id=json_data.get("id", ""),
            name=json_data.get("name", ""),
            selector=json_data.get("selector", []),
            value=json_data.get("value", ""),
            value_type=json_data.get("value_type", ""),
        )


class DefaultValue:
    __slots__ = ["value", "type", "key"]

    value: Any
    type: DefaultValueType
    key: str

    def __init__(self, *, value: Any, type: DefaultValueType, key: str) -> None:
        self.value = value
        self.type = type
        self.key = key

    @classmethod
    def from_json(cls, json_data: dict) -> "DefaultValue":
        if "value" not in json_data:
            raise ValueError("value not found")

        if "type" not in json_data:
            raise ValueError("type not found")

        if "key" not in json_data:
            raise ValueError("key not found")

        return cls(
            value=json_data.get("value", ""),
            type=DefaultValueType.value_of(json_data.get("type")),
            key=json_data.get("key", ""),
        )


class VariableOperationItem:
    variable_selector: Sequence[str]
    input_type: AssignerInputType
    operation: AssignerOperation
    # NOTE(QuantumGhost): The `value` field serves multiple purposes depending on context:
    #
    # 1. For CONSTANT input_type: Contains the literal value to be used in the operation.
    # 2. For VARIABLE input_type: Initially contains the selector of the source variable.
    # 3. During the variable updating procedure: The `value` field is reassigned to hold
    #    the resolved actual value that will be applied to the target variable.
    value: Any | None = None
    # write_mode: str = "over-write"


class LLMNodeModelConfig:
    __slots__ = ["mode", "name", "provider", "completion_params"]

    mode: Literal["chat", "completion"]
    name: str
    provider: str

    # completion_params : dict[str, Any] = {}

    def __init__(
        self, *, mode: str, name: str, provider: str, completion_params: Dict
    ) -> None:
        self.mode = mode
        self.name = name
        self.provider = provider
        self.completion_params = completion_params


class MemoryConfig:
    """memory:
    query_prompt_template: '{{#sys.query#}}'
    role_prefix:
      assistant: ''
      user: ''
    window:
      enabled: false
      size: 50
    """

    __slots__ = ["query_prompt_template", "role_prefix", "window"]

    query_prompt_template: str
    role_prefix: dict[str, str]
    window: dict

    def __init__(
        self,
        *,
        query_prompt_template: str = "",
        role_prefix: dict = None,
        window: dict = None,
    ):
        self.query_prompt_template = query_prompt_template
        self.role_prefix = role_prefix or {}
        self.window = window or {}


class QuestionClassConfig:
    __slots__ = ["id", "name"]

    id: str
    name: str

    def __init__(self, *, id: str, name: str) -> None:
        self.id = id
        self.name = name


class AggregatorAdvancedSettings:
    """
    Advanced setting.
    """

    __slots__ = ["group_enabled", "groups"]

    class Group:
        """
        Group.
        """

        output_type: str
        variables: list[list[str]]
        group_name: str

    group_enabled: bool
    groups: list[Group]


SupportedComparisonOperator = Literal[
    # for string or array
    "contains",
    "not contains",
    "start with",
    "end with",
    "is",
    "is not",
    "empty",
    "not empty",
    "in",
    "not in",
    "all of",
    # for number
    "=",
    "≠",
    ">",
    "<",
    "≥",
    "≤",
    "null",
    "not null",
    # for file
    "exists",
    "not exists",
]


class SubCondition:
    __slots__ = ["key", "comparison_operator", "value"]

    key: str
    comparison_operator: SupportedComparisonOperator
    value: str | Sequence[str] | None


class SubVariableCondition:
    __slots__ = ["logical_operator", "conditions"]

    logical_operator: Literal["and", "or"]
    conditions: list[SubCondition]
    
    def __init__(
        self,
        *,
        logical_operator: Literal["and", "or"],
        conditions: list[SubCondition]
    ):
        self.logical_operator = logical_operator
        self.conditions = conditions


class Condition:
    __slots__ = [
        "variable_selector",
        "comparison_operator",
        "value",
        "sub_variable_condition",
        "varType",
    ]

    variable_selector: list[str]
    """
    variable selector, in the format ["2342342342", "result"]
    where the first item is usually the id of the variable output node
    """

    comparison_operator: SupportedComparisonOperator
    """
    comparison operator
    """

    value: str | Sequence[str] | None
    """
    the configured condition value; if sub_variable_condition is present then value is None
    """

    varType: Literal[
        "number", "string", "array[file]", "array[string]", "array[number]"
    ]

    sub_variable_condition: SubVariableCondition | None
    """
    value and sub_variable_condition are mutually exclusive
    when varType is array and value is None, sub_variable_condition is required
    """

    id: str | None

    def __init__(
        self,
        *,
        variable_selector: list[str],
        comparison_operator: SupportedComparisonOperator,
        value: str | Sequence[str] | None,
        varType: Literal[
            "number", "string", "array[file]", "array[string]", "array[number]"
        ],
        sub_variable_condition: Optional[SubVariableCondition] = None,
    ):
        self.variable_selector = variable_selector
        self.comparison_operator = comparison_operator
        self.value = value
        self.varType = varType
        self.sub_variable_condition = sub_variable_condition


class Case:
    """
    Case entity representing a single logical condition group
    """

    __slots__ = ["case_id", "logical_operator", "conditions"]

    case_id: str
    logical_operator: Literal["and", "or"]
    conditions: list[Condition]

    def __init__(
        self,
        *,
        case_id: str,
        logical_operator: Literal["and", "or"],
        conditions: list[Condition],
    ):
        self.case_id = case_id
        self.logical_operator = logical_operator
        self.conditions = conditions


class ContextConfig:
    __slots__ = ["enabled", "variable_selector"]

    enabled: bool
    variable_selector: Optional[list[str]]

    def __init__(
        self, *, enabled: bool = False, variable_selector: Optional[list[str]] = None
    ) -> None:
        self.enabled = enabled
        self.variable_selector = variable_selector


class VisionConfigOptions:
    variable_selector: Sequence[str]
    detail: str

    def __init__(
        self,
        *,
        variable_selector: Sequence[str] = ["sys", "files"],
        detail: str = "high",
    ) -> None:
        self.variable_selector = variable_selector
        self.detail = detail


class VisionConfig:
    enabled: bool
    configs: Optional[VisionConfigOptions]

    def __init__(
        self, *, enabled: bool, configs: Optional[VisionConfigOptions] = None
    ) -> None:
        self.enabled = enabled
        self.configs = configs


class LLmNodePromptTemplate:
    """
    prompt template config of an llm node
    """

    __slots__ = ["id", "role", "text", "multimodal_content","jinja2_text", "edition_type"]

    id: str
    role: Literal["user", "assistant", "system"]
    text: str
    multimodal_content:Optional[list[dict]] 
    jinja2_text: Optional[str]
    edition_type: Optional[Literal["jinja2", "basic"]]

    def __init__(
        self,
        *,
        id: Optional[str] = None,
        role: Literal["user", "assistant", "system"],
        text: str,
        multimodal_content:Optional[list[dict]] = None,
        jinja2_text: Optional[str] = None,
        edition_type: Optional[Literal["jinja2", "basic"]] = None,
    ) -> None:
        self.id = id
        self.role = role
        self.text = text
        self.multimodal_content = multimodal_content
        self.jinja2_text = jinja2_text
        self.edition_type = edition_type


class PromptConfig:
    __slots__ = ["jinja2_variables"]
    jinja2_variables: Sequence[NodeVarConfig]

    def __init__(self, *, jinja2_variables: Sequence[NodeVarConfig]) -> None:
        self.jinja2_variables = jinja2_variables


class LoopVariableData:
    """
    Loop Variable Data.
    """

    __slots__ = ["id", "label", "var_type", "value_type", "value"]

    id: str
    label: str
    var_type: str
    value_type: Literal["variable", "constant"]
    value: Optional[Any | list[str]]

    def __init__(
        self,
        id: str,
        label: str,
        var_type: str,
        value_type: Literal["variable", "constant"],
        value: Optional[Any | list[str]] = None,
    ):
        self.id = id
        self.label = label
        self.var_type = var_type
        self.value_type = value_type
        self.value = value


class WfVariableConfig:
    """
    Variable Entity.
    """

    __slots__ = [
        "variable",
        "label",
        "description",
        "type",
        "required",
        "hide",
        "max_length",
        "options",
        "allowed_file_types",
        "allowed_file_extensions",
        "allowed_file_upload_methods",
        "default",
        "hint",
        "placeholder",
    ]

    # `variable` records the name of the variable in user inputs.
    variable: str
    label: str
    description: str
    type: VariableEntityType
    required: bool
    hide: bool
    max_length: Optional[int]
    options: Sequence[str]
    allowed_file_types: Sequence[str]
    allowed_file_extensions: Sequence[str]
    allowed_file_upload_methods: Sequence[FileTransferMethod]
    default: Optional[Any]
    hint: Optional[str]
    placeholder: Optional[str]

    def __init__(
        self,
        *,
        variable: str,
        label: str,
        description: str = "",
        type: str,
        required: bool = False,
        hide: bool = False,
        max_length: Optional[int] = None,
        options: Sequence[str] = [],
        allowed_file_types: Sequence[str] = [],
        allowed_file_extensions: Sequence[str] = [],
        allowed_file_upload_methods: Sequence[FileTransferMethod] = [],
        default: Optional[Any] = None,
        hint: Optional[str] = None ,
        placeholder: Optional[str] = None,
    ) -> None:
        self.variable = variable
        self.label = label
        self.description = description
        self.type = type
        self.required = required
        self.hide = hide
        self.max_length = max_length
        self.options = options
        self.allowed_file_types = allowed_file_types
        self.allowed_file_extensions = allowed_file_extensions
        self.allowed_file_upload_methods = allowed_file_upload_methods
        self.default = default
        self.hint = hint
        self.placeholder = placeholder

    def to_json(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "required": self.required,
            "hide": self.hide,
            "max_length": self.max_length,
            "options": self.options,
            "allowed_file_types": self.allowed_file_types,
            "allowed_file_extensions": self.allowed_file_extensions,
            "allowed_file_upload_methods": [
                method for method in self.allowed_file_upload_methods
            ],
        }

    @staticmethod
    def from_json(data: dict[str, Any]) -> "WfVariableConfig":
        return WfVariableConfig(
            variable=data["variable"],
            label=data["label"],
            description=data.get("description", ""),
            type=data["type"],
            required=data.get("required", False),
            hide=data.get("hide", False),
            max_length=data.get("max_length", None),
            options=data.get("options", []),
            allowed_file_types=data.get("allowed_file_types", []),
            allowed_file_extensions=data.get("allowed_file_extensions", []),
            allowed_file_upload_methods=data.get("allowed_file_upload_methods", []),
        )

class File:
    __slots__ = ["type", "transfer_method", "remote_url"]
    type: FileType
    transfer_method: FileTransferMethod
    remote_url: Optional[str]

    def __init__(
        self,
        *,
        type: FileType,
        transfer_method: FileTransferMethod,
        remote_url: Optional[str] = None,
    ) -> None:
        self.type = type
        self.transfer_method = transfer_method
        self.remote_url = remote_url


class HttpRequestBodyConfigItem:
    __slots__ = ["id", "key", "type", "value"]

    id: str
    key: str
    type: Literal["file", "text"]
    value: str

    def __init__(
        self, *, id: str, key: str, type: Literal["file", "text"], value: str
    ) -> None:
        self.id = id
        self.key = key
        self.type = type
        self.value = value


class HttpRequestBodyConfig:
    __slots__ = ["data", "type"]

    data: Sequence[HttpRequestBodyConfigItem]
    type: Literal[
        "none", "form-data", "x-www-form-urlencoded", "raw-text", "json", "binary"
    ]

    # def __init__(self, * ,data : Sequence[HttpRequestBodyConfigItem],type: Literal["none", "form-data", "x-www-form-urlencoded", "raw-text", "json", "binary"]) -> None:
    #     self.data = data
    #     self.type = type


DifyAuthType = Literal["no-auth", "api-key"]
DifyApiKeyType = Literal["basic", "bearer", "custom"]


class HttpNodeApiKeyConfig:
    __slots__ = ["api_key", "header", "type"]

    api_key: str
    header: str
    type: str


class HttpNodeAuthorizationConfig:
    __slots__ = ["config", "type"]

    config: HttpNodeApiKeyConfig
    type: DifyAuthType

    def __init__(
        self,
        *,
        config: Optional[HttpNodeApiKeyConfig] = None,
        type: Optional[DifyAuthType] = None,
    ) -> None:
        self.config = config
        self.type = type


class HttpNodeRetryConfig:
    __slots__ = ["max_retries", "retry_enabled", "retry_interval"]
    # max number of retries
    max_retries: int
    # whether retry is enabled
    retry_enabled: bool
    # retry interval, in milliseconds
    retry_interval: int

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_enabled: bool = True,
        retry_interval: int = 1000,
    ) -> None:
        self.max_retries = max_retries
        self.retry_enabled = retry_enabled
        self.retry_interval = retry_interval


class HttpNodeTimeoutConfig:
    __slots__ = ["max_connect_timeout", "max_read_timeout", "max_write_timeout"]
    # connect timeout, in seconds
    max_connect_timeout: int
    # read timeout, in seconds
    max_read_timeout: int
    # write timeout, in seconds
    max_write_timeout: int

    def __init__(
        self,
        *,
        max_connect_timeout: int = 10,
        max_read_timeout: int = 60,
        max_write_timeout: int = 10,
    ) -> None:
        self.max_connect_timeout = max_connect_timeout
        self.max_read_timeout = max_read_timeout
        self.max_write_timeout = max_write_timeout


class ToolInput:
    value: Union[str, list[str], Any]
    type: Literal["mixed", "variable", "constant"]

    def __init__(
        self, *, value: str, type: Literal["mixed", "variable", "constant"]
    ) -> None:
        self.value = value
        self.type = type

    def to_json(self) -> dict:
        return {
            "value": self.value,
            "type": self.type,
        }

    @staticmethod
    def from_json(key: str, json_data: dict) -> "ToolInput":
        return {
            key: ToolInput(
                value=json_data.get("value", ""),
                type=json_data.get("type", "mixed"),
            )
        }

    @staticmethod
    def from_json2(json_data: dict) -> "ToolInput":
        return ToolInput(value=json_data.get("value"), type=json_data.get("type"))


class ToolParams:
    file_name: str
    raw_text: str


class ToolParamSchema:
    auto_generate: str
    default: Any
    form: str
    human_description: Dict[str, str]
    label: Dict[str, str]
    llm_description: str
    max: int | None
    min: int | None
    name: str
    options: List[Any]
    placeholder: Dict[str, str]
    precision: Optional[Any]
    required: bool
    scope: Optional[Any]
    template: Optional[Any]
    type: str

    def __init__(
        self,
        *,
        auto_generate: str,
        default: Any,
        form: str,
        human_description: Dict[str, str],
        label: Dict[str, str],
        llm_description: str,
        max: int | None,
        min: int | None,
        name: str,
        options: List[Any],
        placeholder: Dict[str, str],
        precision: Optional[Any],
        required: bool,
        scope: Optional[Any],
        template: Optional[Any],
        type: str,
    ) -> None:
        self.auto_generate = auto_generate
        self.default = default
        self.form = form
        self.human_description = human_description
        self.label = label
        self.llm_description = llm_description
        self.max = max
        self.min = min
        self.name = name
        self.options = options
        self.placeholder = placeholder
        self.precision = precision
        self.required = required
        self.scope = scope
        self.template = template
        self.type = type

    @staticmethod
    def from_json(json_data: dict) -> "ToolParamSchema":
        return ToolParamSchema(
            auto_generate=json_data.get("auto_generate", ""),
            default=json_data.get("default", None),
            form=json_data.get("form", ""),
            human_description=json_data.get("human_description", {}),
            label=json_data.get("label", {}),
            llm_description=json_data.get("llm_description", ""),
            max=json_data.get("max", None),
            min=json_data.get("min", None),
            name=json_data.get("name", ""),
            options=json_data.get("options", []),
            placeholder=json_data.get("placeholder", {}),
            precision=json_data.get("precision", None),
            required=json_data.get("required", False),
            scope=json_data.get("scope", None),
            template=json_data.get("template", None),
            type=json_data.get("type", ""),
        )


class ToolProviderConfig:
    provider_id: str
    provider_type: ToolProviderType
    provider_name: str  # redundancy
    tool_name: str
    tool_label: str  # redundancy
    tool_configurations: dict[str, Any]
    credential_id: str | None = None
    plugin_unique_identifier: str | None = None  # redundancy
    tool_parameters: dict[str, ToolInput]


# Agent
class AgentToolParameterConfig:
    """
    Agent Tool Value Parameter
    """

    auto: int
    value: Optional[Any]

    def __init__(self, auto: int, value: Optional[Any] = None) -> None:
        self.auto = auto
        self.value = value


class AgentToolValueConfig:
    """
    Agent Tools Value Config
    """

    enabled: bool
    extra: Dict[str, Any]
    parameters: Dict[str, AgentToolParameterConfig]
    # corresponds to the id of the dify database table tool_workflow_providers
    provider_name: str
    schemas: Optional[list[ToolParamSchema]]
    func: Optional[Callable] = None
    settings: Optional[dict[str, Any]]
    tool_label: str
    tool_name: str
    type: str


class AgentToolConfig:
    """
    Agent Tools Config
    """

    type: str
    value: Optional[list[AgentToolValueConfig]]
    
    
ConversationVarTypeStr = Literal[
    "string",
    "number",
    "object",
    "array[string]",
    "array[number]",
    "array[object]"
]


class ConversationVar:
    
    __slots__ = ["description","name","id","value","value_type","selector"]
    
    description : str
    name : str
    id : str
    value : str
    value_type : ConversationVarTypeStr
    selector : Optional[List[str]]
    
    def __init__(self, * ,description : str, name : str, id : str, value : str, value_type : str, selector : Optional[List[str]] = None) -> None:
        self.description = description
        self.name = name
        self.id = id
        self.value = value
        self.value_type = value_type
        self.selector = selector
        
        
    def to_json(self) -> dict:
        return {
            "description": self.description,
            "name": self.name,
            "id": self.id,
            "value": self.value,
            "value_type": self.value_type,
            "selector": self.selector,
        }
        
    @staticmethod
    def from_json(json_data: dict) -> "ConversationVar":
        return ConversationVar(
            description=json_data.get("description", ""),
            name=json_data.get("name", ""),
            id=json_data.get("id", ""),
            value=json_data.get("value", ""),
            value_type=json_data.get("value_type", ""),
            selector=json_data.get("selector", None),
        )


from typing import Protocol

class InterruptHook(Protocol):
    def after_interrupt(self, interrupt: Interrupt) -> object: ...